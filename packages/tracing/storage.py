"""
SQLite/PostgreSQL storage for runs and spans.

Uses SQLAlchemy Core (not ORM) for minimal overhead on the agent's critical path.
Target: < 100ms overhead per span write.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
    update,
    and_,
    or_,
    func,
)
from sqlalchemy.pool import StaticPool

from packages.tracing.models import Run, Span, RunStatus, SpanStatus, SpanKind, SpanEvent

_engine = None
_metadata = MetaData()

# ─────────────────────────── Table Definitions ────────────────────────────

runs_table = Table(
    "runs",
    _metadata,
    Column("run_id", String(32), primary_key=True),
    Column("trace_id", String(32), nullable=False, index=True),
    Column("agent_type", String(64), nullable=False, index=True),
    Column("benchmark", String(64), nullable=False, index=True),
    Column("task_id", String(128), nullable=False),
    Column("model_name", String(128), nullable=False),
    Column("model_provider", String(64), nullable=False),
    Column("prompt_version", String(32), nullable=False),
    Column("framework", String(64), nullable=False),
    Column("status", String(32), nullable=False, index=True),
    Column("created_at", DateTime, nullable=False, index=True),
    Column("completed_at", DateTime, nullable=True),
    Column("total_steps", Integer, default=0),
    Column("total_tokens", Integer, default=0),
    Column("total_cost_usd", Float, default=0.0),
    Column("total_latency_ms", Float, default=0.0),
    Column("policy_violations", Text, default="[]"),   # JSON
    Column("hitl_required", Integer, default=0),        # bool as int
    Column("eval_scores", Text, default="{}"),          # JSON
    Column("tags", Text, default="{}"),                 # JSON
    Column("config", Text, default="{}"),               # JSON
)

spans_table = Table(
    "spans",
    _metadata,
    Column("span_id", String(32), primary_key=True),
    Column("trace_id", String(32), nullable=False, index=True),
    Column("run_id", String(32), nullable=False, index=True),
    Column("parent_span_id", String(32), nullable=True),
    Column("name", String(256), nullable=False),
    Column("kind", String(32), nullable=False),
    Column("start_time", DateTime, nullable=False),
    Column("end_time", DateTime, nullable=True),
    Column("duration_ms", Float, nullable=True),
    Column("input_payload", Text, default="{}"),
    Column("output_payload", Text, default="{}"),
    Column("attributes", Text, default="{}"),
    Column("events", Text, default="[]"),
    Column("status", String(16), nullable=False),
    Column("error_message", Text, nullable=True),
    Column("prompt_tokens", Integer, default=0),
    Column("completion_tokens", Integer, default=0),
    Column("total_tokens", Integer, default=0),
    Column("estimated_cost_usd", Float, default=0.0),
)

policy_events_table = Table(
    "policy_events",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(32), nullable=False, index=True),
    Column("span_id", String(32), nullable=True),
    Column("policy_name", String(64), nullable=False),
    Column("action", String(32), nullable=False),  # blocked | allowed | hitl
    Column("severity", String(16), nullable=False),
    Column("reason", Text, nullable=False),
    Column("tool_name", String(64), nullable=True),
    Column("tool_input", Text, default="{}"),
    Column("created_at", DateTime, nullable=False),
)


def _get_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///./data/arl.db")
    return url


def get_engine():
    global _engine
    if _engine is None:
        url = _get_db_url()
        kwargs: dict[str, Any] = {}
        if url.startswith("sqlite"):
            # SQLite-specific: allow same-thread = False for async use
            kwargs = {
                "connect_args": {"check_same_thread": False},
                "poolclass": StaticPool,
            }
        _engine = create_engine(url, **kwargs)
        _metadata.create_all(_engine)
    return _engine


class TraceStorage:
    """Synchronous storage backend for runs and spans."""

    def __init__(self, database_url: str | None = None):
        self._engine = get_engine()

    # ─────────────────────────── Runs ─────────────────────────────────

    def save_run(self, run: Run) -> None:
        """Insert or update a run record."""
        with self._engine.begin() as conn:
            existing = conn.execute(
                select(runs_table).where(runs_table.c.run_id == run.run_id)
            ).fetchone()

            row = self._run_to_row(run)
            if existing:
                conn.execute(
                    update(runs_table)
                    .where(runs_table.c.run_id == run.run_id)
                    .values(**{k: v for k, v in row.items() if k != "run_id"})
                )
            else:
                conn.execute(insert(runs_table).values(**row))

        # Upsert all spans
        for span in run.spans:
            self.save_span(span, run.run_id)

    def get_run(self, run_id: str) -> Run | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(runs_table).where(runs_table.c.run_id == run_id)
            ).fetchone()
            if not row:
                return None
            run = self._row_to_run(row)
            # Load spans
            spans = self._load_spans_for_run(conn, run_id)
            run.spans = spans
            return run

    def list_runs(
        self,
        *,
        agent_type: str | None = None,
        benchmark: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Run]:
        with self._engine.connect() as conn:
            q = select(runs_table).order_by(runs_table.c.created_at.desc())
            filters = []
            if agent_type:
                filters.append(runs_table.c.agent_type == agent_type)
            if benchmark:
                filters.append(runs_table.c.benchmark == benchmark)
            if status:
                filters.append(runs_table.c.status == status)
            if filters:
                q = q.where(and_(*filters))
            q = q.limit(limit).offset(offset)
            rows = conn.execute(q).fetchall()
            runs = []
            for row in rows:
                run = self._row_to_run(row)
                run.spans = self._load_spans_for_run(conn, run.run_id)
                runs.append(run)
            return runs

    def count_runs(self) -> int:
        with self._engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(runs_table)).scalar() or 0

    # ─────────────────────────── Spans ────────────────────────────────

    def save_span(self, span: Span, run_id: str) -> None:
        with self._engine.begin() as conn:
            existing = conn.execute(
                select(spans_table).where(spans_table.c.span_id == span.span_id)
            ).fetchone()
            row = self._span_to_row(span, run_id)
            if existing:
                conn.execute(
                    update(spans_table)
                    .where(spans_table.c.span_id == span.span_id)
                    .values(**{k: v for k, v in row.items() if k != "span_id"})
                )
            else:
                conn.execute(insert(spans_table).values(**row))

    def get_spans_for_run(self, run_id: str) -> list[Span]:
        with self._engine.connect() as conn:
            return self._load_spans_for_run(conn, run_id)

    # ─────────────────────────── Policy Events ────────────────────────

    def save_policy_event(
        self,
        run_id: str,
        span_id: str | None,
        policy_name: str,
        action: str,
        severity: str,
        reason: str,
        tool_name: str | None = None,
        tool_input: dict | None = None,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(policy_events_table).values(
                    run_id=run_id,
                    span_id=span_id,
                    policy_name=policy_name,
                    action=action,
                    severity=severity,
                    reason=reason,
                    tool_name=tool_name,
                    tool_input=json.dumps(tool_input or {}),
                    created_at=datetime.now(timezone.utc),
                )
            )

    def get_policy_events(self, run_id: str) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(policy_events_table).where(
                    policy_events_table.c.run_id == run_id
                )
            ).fetchall()
            return [dict(r._mapping) for r in rows]

    # ─────────────────────────── Leaderboard ──────────────────────────

    def leaderboard(self, benchmark: str | None = None) -> list[dict]:
        """Return aggregated stats per (model_name × framework × benchmark)."""
        with self._engine.connect() as conn:
            q = select(
                runs_table.c.model_name,
                runs_table.c.model_provider,
                runs_table.c.framework,
                runs_table.c.benchmark,
                func.count(runs_table.c.run_id).label("total_runs"),
                func.avg(runs_table.c.total_latency_ms).label("avg_latency_ms"),
                func.avg(runs_table.c.total_tokens).label("avg_tokens"),
                func.avg(runs_table.c.total_cost_usd).label("avg_cost_usd"),
            ).where(runs_table.c.status == RunStatus.COMPLETED.value)
            if benchmark:
                q = q.where(runs_table.c.benchmark == benchmark)
            q = q.group_by(
                runs_table.c.model_name,
                runs_table.c.model_provider,
                runs_table.c.framework,
                runs_table.c.benchmark,
            ).order_by(func.avg(runs_table.c.total_latency_ms))
            rows = conn.execute(q).fetchall()
            return [dict(r._mapping) for r in rows]

    # ─────────────────────────── Helpers ──────────────────────────────

    def _run_to_row(self, run: Run) -> dict:
        return {
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "agent_type": run.agent_type,
            "benchmark": run.benchmark,
            "task_id": run.task_id,
            "model_name": run.model_name,
            "model_provider": run.model_provider,
            "prompt_version": run.prompt_version,
            "framework": run.framework,
            "status": run.status.value,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
            "total_steps": run.total_steps,
            "total_tokens": run.total_tokens,
            "total_cost_usd": run.total_cost_usd,
            "total_latency_ms": run.total_latency_ms,
            "policy_violations": json.dumps(run.policy_violations),
            "hitl_required": 1 if run.hitl_required else 0,
            "eval_scores": json.dumps(run.eval_scores),
            "tags": json.dumps(run.tags),
            "config": json.dumps(run.config),
        }

    def _row_to_run(self, row) -> Run:
        d = dict(row._mapping)
        return Run(
            run_id=d["run_id"],
            trace_id=d["trace_id"],
            agent_type=d["agent_type"],
            benchmark=d["benchmark"],
            task_id=d["task_id"],
            model_name=d["model_name"],
            model_provider=d["model_provider"],
            prompt_version=d["prompt_version"],
            framework=d["framework"],
            status=RunStatus(d["status"]),
            created_at=d["created_at"],
            completed_at=d.get("completed_at"),
            total_steps=d.get("total_steps", 0),
            total_tokens=d.get("total_tokens", 0),
            total_cost_usd=d.get("total_cost_usd", 0.0),
            total_latency_ms=d.get("total_latency_ms", 0.0),
            policy_violations=json.loads(d.get("policy_violations") or "[]"),
            hitl_required=bool(d.get("hitl_required", 0)),
            eval_scores=json.loads(d.get("eval_scores") or "{}"),
            tags=json.loads(d.get("tags") or "{}"),
            config=json.loads(d.get("config") or "{}"),
            spans=[],
        )

    def _span_to_row(self, span: Span, run_id: str) -> dict:
        return {
            "span_id": span.span_id,
            "trace_id": span.trace_id,
            "run_id": run_id,
            "parent_span_id": span.parent_span_id,
            "name": span.name,
            "kind": span.kind.value,
            "start_time": span.start_time,
            "end_time": span.end_time,
            "duration_ms": span.duration_ms,
            "input_payload": json.dumps(span.input_payload),
            "output_payload": json.dumps(span.output_payload),
            "attributes": json.dumps(span.attributes),
            "events": json.dumps([e.model_dump(mode="json") for e in span.events]),
            "status": span.status.value,
            "error_message": span.error_message,
            "prompt_tokens": span.prompt_tokens,
            "completion_tokens": span.completion_tokens,
            "total_tokens": span.total_tokens,
            "estimated_cost_usd": span.estimated_cost_usd,
        }

    def _row_to_span(self, row) -> Span:
        d = dict(row._mapping)
        events_raw = json.loads(d.get("events") or "[]")
        events = [SpanEvent(**e) for e in events_raw]
        return Span(
            span_id=d["span_id"],
            trace_id=d["trace_id"],
            parent_span_id=d.get("parent_span_id"),
            name=d["name"],
            kind=SpanKind(d["kind"]),
            start_time=d["start_time"],
            end_time=d.get("end_time"),
            duration_ms=d.get("duration_ms"),
            input_payload=json.loads(d.get("input_payload") or "{}"),
            output_payload=json.loads(d.get("output_payload") or "{}"),
            attributes=json.loads(d.get("attributes") or "{}"),
            events=events,
            status=SpanStatus(d["status"]),
            error_message=d.get("error_message"),
            prompt_tokens=d.get("prompt_tokens", 0),
            completion_tokens=d.get("completion_tokens", 0),
            total_tokens=d.get("total_tokens", 0),
            estimated_cost_usd=d.get("estimated_cost_usd", 0.0),
        )

    def _load_spans_for_run(self, conn, run_id: str) -> list[Span]:
        rows = conn.execute(
            select(spans_table)
            .where(spans_table.c.run_id == run_id)
            .order_by(spans_table.c.start_time)
        ).fetchall()
        return [self._row_to_span(r) for r in rows]


# ─────────────────────────── Singleton ────────────────────────────────────

_storage: TraceStorage | None = None


def get_storage() -> TraceStorage:
    global _storage
    if _storage is None:
        os.makedirs("data", exist_ok=True)
        _storage = TraceStorage()
    return _storage
