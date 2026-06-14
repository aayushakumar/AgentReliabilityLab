"""
Tracing data models for AgentReliabilityLab.

Implements OTel-compatible span/trace data structures stored in SQLite/PostgreSQL.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


class SpanStatus(str, Enum):
    """Terminal status of a span."""
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


class SpanKind(str, Enum):
    """Semantic kind of a span, following OTel conventions."""
    INTERNAL = "internal"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    RETRIEVAL = "retrieval"
    POLICY_CHECK = "policy_check"
    PLANNER = "planner"
    HITL = "hitl"
    FINAL_ANSWER = "final_answer"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    HITL_WAITING = "hitl_waiting"


class SpanEvent(BaseModel):
    """An event recorded within a span."""
    name: str
    timestamp: datetime = Field(default_factory=_now)
    attributes: dict[str, Any] = Field(default_factory=dict)


class Span(BaseModel):
    """
    OTel-compatible span representing one step in an agent execution.

    Fields mirror the OpenTelemetry Span spec:
    https://opentelemetry.io/docs/concepts/signals/traces/
    """
    span_id: str = Field(default_factory=_new_id)
    trace_id: str = ""          # set by Run when span is added
    parent_span_id: str | None = None

    name: str
    kind: SpanKind = SpanKind.INTERNAL

    start_time: datetime = Field(default_factory=_now)
    end_time: datetime | None = None
    duration_ms: float | None = None

    # Input/output payloads (stored as JSON strings in DB)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)

    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[SpanEvent] = Field(default_factory=list)

    status: SpanStatus = SpanStatus.UNSET
    error_message: str | None = None

    # Token / cost accounting
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def end(
        self,
        *,
        output: dict[str, Any] | None = None,
        status: SpanStatus = SpanStatus.OK,
        error: str | None = None,
    ) -> "Span":
        """Finalise the span and compute duration."""
        self.end_time = _now()
        self.duration_ms = (
            (self.end_time - self.start_time).total_seconds() * 1000
        )
        self.status = status
        if output:
            self.output_payload = output
        if error:
            self.error_message = error
            self.status = SpanStatus.ERROR
        return self

    def add_event(self, name: str, **attrs: Any) -> None:
        self.events.append(SpanEvent(name=name, attributes=attrs))

    def set_token_usage(
        self, prompt: int = 0, completion: int = 0, cost_usd: float = 0.0
    ) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = prompt + completion
        self.estimated_cost_usd = cost_usd


class Run(BaseModel):
    """
    A complete agent execution, composed of one or more Spans.

    The run is the top-level unit of evaluation — each benchmark task
    produces one Run.
    """
    run_id: str = Field(default_factory=_new_id)
    trace_id: str = Field(default_factory=_new_id)

    agent_type: str          # sql_agent | rag_agent | security_agent
    benchmark: str           # sql_agent | enterprise_rag | github_security
    task_id: str             # foreign key to benchmark task

    model_name: str = "unknown"
    model_provider: str = "unknown"
    prompt_version: str = "v1"
    framework: str = "langgraph"

    status: RunStatus = RunStatus.PENDING
    created_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None

    spans: list[Span] = Field(default_factory=list)

    # Aggregate metrics (computed after run completes)
    total_steps: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0

    # Policy / safety
    policy_violations: list[dict[str, Any]] = Field(default_factory=list)
    hitl_required: bool = False

    # Eval results (filled after grading)
    eval_scores: dict[str, float] = Field(default_factory=dict)

    # Metadata / tags
    tags: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_span_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
    ) -> Span:
        """Create, register, and return a new child span."""
        span = Span(
            name=name,
            kind=kind,
            parent_span_id=parent_span_id,
            trace_id=self.trace_id,
            input_payload=input_payload or {},
        )
        span.trace_id = self.trace_id
        self.spans.append(span)
        return span

    def complete(self, status: RunStatus = RunStatus.COMPLETED) -> None:
        self.status = status
        self.completed_at = _now()
        self.total_steps = len(self.spans)
        self.total_tokens = sum(s.total_tokens for s in self.spans)
        self.total_cost_usd = sum(s.estimated_cost_usd for s in self.spans)
        if self.spans:
            first = min(s.start_time for s in self.spans)
            last_end = max(
                (s.end_time or s.start_time) for s in self.spans
            )
            self.total_latency_ms = (
                (last_end - first).total_seconds() * 1000
            )

    def get_span(self, span_id: str) -> Span | None:
        return next((s for s in self.spans if s.span_id == span_id), None)

    def get_spans_by_kind(self, kind: SpanKind) -> list[Span]:
        return [s for s in self.spans if s.kind == kind]
