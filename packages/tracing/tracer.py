"""
Tracer — context-manager API for creating and exporting spans.

Usage:
    tracer = get_tracer()
    run = tracer.start_run(agent_type="sql_agent", ...)
    with tracer.span(run, "llm_call", kind=SpanKind.LLM_CALL) as span:
        span.input_payload = {"prompt": "..."}
        result = llm.invoke(...)
        span.output_payload = {"response": str(result)}
    tracer.finish_run(run)
"""
from __future__ import annotations

import contextlib
import logging
from typing import Any, Generator

from packages.tracing.models import Run, Span, SpanKind, SpanStatus, RunStatus
from packages.tracing.storage import TraceStorage, get_storage

logger = logging.getLogger(__name__)


class Tracer:
    """
    Lightweight tracer that creates Runs and Spans and persists them.

    Designed for < 5ms overhead per span on the critical path.
    """

    def __init__(self, storage: TraceStorage | None = None):
        self._storage = storage or get_storage()

    # ─────────────────────────── Run Lifecycle ─────────────────────────

    def start_run(
        self,
        *,
        agent_type: str,
        benchmark: str,
        task_id: str,
        model_name: str = "unknown",
        model_provider: str = "unknown",
        prompt_version: str = "v1",
        framework: str = "langgraph",
        tags: dict[str, str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> Run:
        """Create a new Run and persist it immediately."""
        run = Run(
            agent_type=agent_type,
            benchmark=benchmark,
            task_id=task_id,
            model_name=model_name,
            model_provider=model_provider,
            prompt_version=prompt_version,
            framework=framework,
            status=RunStatus.RUNNING,
            tags=tags or {},
            config=config or {},
        )
        self._storage.save_run(run)
        logger.debug("Started run %s for task %s", run.run_id, task_id)
        return run

    def finish_run(
        self, run: Run, status: RunStatus = RunStatus.COMPLETED
    ) -> Run:
        """Complete the run, compute aggregates, and persist."""
        run.complete(status)
        self._storage.save_run(run)
        logger.debug(
            "Finished run %s status=%s latency=%.0fms",
            run.run_id,
            run.status.value,
            run.total_latency_ms,
        )
        return run

    # ─────────────────────────── Span Lifecycle ────────────────────────

    @contextlib.contextmanager
    def span(
        self,
        run: Run,
        name: str,
        *,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_span_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
    ) -> Generator[Span, None, None]:
        """Context manager that starts, yields, and ends a span."""
        s = run.start_span(
            name,
            kind=kind,
            parent_span_id=parent_span_id,
            input_payload=input_payload,
        )
        try:
            yield s
        except Exception as exc:
            s.end(status=SpanStatus.ERROR, error=str(exc))
            self._storage.save_span(s, run.run_id)
            raise
        else:
            if s.end_time is None:
                s.end(status=SpanStatus.OK)
            self._storage.save_span(s, run.run_id)

    def manual_span(
        self,
        run: Run,
        name: str,
        *,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_span_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
    ) -> Span:
        """Create a span manually — caller must call span.end() and save_span()."""
        return run.start_span(
            name,
            kind=kind,
            parent_span_id=parent_span_id,
            input_payload=input_payload,
        )

    def finish_span(self, run: Run, span: Span, **kwargs) -> None:
        span.end(**kwargs)
        self._storage.save_span(span, run.run_id)

    # ─────────────────────────── Policy Events ────────────────────────

    def record_policy_event(
        self,
        run: Run,
        span: Span | None,
        *,
        policy_name: str,
        action: str,
        severity: str,
        reason: str,
        tool_name: str | None = None,
        tool_input: dict | None = None,
    ) -> None:
        """Record a policy block/allow event and attach it to the run."""
        event = {
            "policy_name": policy_name,
            "action": action,
            "severity": severity,
            "reason": reason,
            "tool_name": tool_name,
        }
        run.policy_violations.append(event)
        if action in ("blocked", "hitl"):
            run.hitl_required = action == "hitl"

        self._storage.save_policy_event(
            run_id=run.run_id,
            span_id=span.span_id if span else None,
            policy_name=policy_name,
            action=action,
            severity=severity,
            reason=reason,
            tool_name=tool_name,
            tool_input=tool_input,
        )


# ─────────────────────────── Singleton ────────────────────────────────────

_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer
