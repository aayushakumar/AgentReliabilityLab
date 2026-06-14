"""
Tests for the tracing package.
Coverage target: ≥ 80%
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

from packages.tracing.models import Run, Span, SpanKind, SpanStatus, RunStatus


class TestSpanLifecycle:
    def test_span_creation(self):
        span = Span(name="test_span", kind=SpanKind.LLM_CALL)
        assert span.span_id
        assert span.name == "test_span"
        assert span.kind == SpanKind.LLM_CALL
        assert span.status == SpanStatus.UNSET
        assert span.end_time is None

    def test_span_end_sets_duration(self):
        span = Span(name="test")
        time.sleep(0.01)
        span.end(status=SpanStatus.OK)
        assert span.end_time is not None
        assert span.duration_ms is not None
        assert span.duration_ms >= 10  # at least 10ms

    def test_span_end_with_error(self):
        span = Span(name="test")
        span.end(error="Something went wrong")
        assert span.status == SpanStatus.ERROR
        assert span.error_message == "Something went wrong"

    def test_span_add_event(self):
        span = Span(name="test")
        span.add_event("cache_hit", key="user:123")
        assert len(span.events) == 1
        assert span.events[0].name == "cache_hit"
        assert span.events[0].attributes["key"] == "user:123"

    def test_span_token_usage(self):
        span = Span(name="llm_call", kind=SpanKind.LLM_CALL)
        span.set_token_usage(prompt=100, completion=50, cost_usd=0.001)
        assert span.prompt_tokens == 100
        assert span.completion_tokens == 50
        assert span.total_tokens == 150
        assert span.estimated_cost_usd == 0.001


class TestRunLifecycle:
    def test_run_creation(self):
        run = Run(
            agent_type="sql_agent",
            benchmark="sql_agent",
            task_id="task-001",
        )
        assert run.run_id
        assert run.trace_id
        assert run.status == RunStatus.PENDING

    def test_run_start_span(self):
        run = Run(agent_type="sql_agent", benchmark="sql_agent", task_id="t1")
        span = run.start_span("test", kind=SpanKind.TOOL_CALL)
        assert span in run.spans
        assert span.trace_id == run.trace_id

    def test_run_complete_aggregates(self):
        run = Run(agent_type="sql_agent", benchmark="sql_agent", task_id="t1")
        s1 = run.start_span("span1", kind=SpanKind.LLM_CALL)
        s1.set_token_usage(prompt=100, completion=50, cost_usd=0.001)
        s1.end()
        s2 = run.start_span("span2", kind=SpanKind.TOOL_CALL)
        s2.end()

        run.complete()
        assert run.status == RunStatus.COMPLETED
        assert run.completed_at is not None
        assert run.total_steps == 2
        assert run.total_tokens == 150
        assert run.total_cost_usd == pytest.approx(0.001)
        assert run.total_latency_ms > 0

    def test_run_get_spans_by_kind(self):
        run = Run(agent_type="sql_agent", benchmark="sql_agent", task_id="t1")
        run.start_span("llm1", kind=SpanKind.LLM_CALL)
        run.start_span("tool1", kind=SpanKind.TOOL_CALL)
        run.start_span("llm2", kind=SpanKind.LLM_CALL)

        llm_spans = run.get_spans_by_kind(SpanKind.LLM_CALL)
        assert len(llm_spans) == 2

    def test_run_get_span_by_id(self):
        run = Run(agent_type="sql_agent", benchmark="sql_agent", task_id="t1")
        span = run.start_span("test")
        found = run.get_span(span.span_id)
        assert found is span
        assert run.get_span("nonexistent") is None


class TestTracer:
    def test_start_and_finish_run(self, tracer):
        run = tracer.start_run(
            agent_type="sql_agent",
            benchmark="sql_agent",
            task_id="test-001",
            model_name="gpt-4o-mini",
            model_provider="openai",
        )
        assert run.run_id
        assert run.status == RunStatus.RUNNING

        tracer.finish_run(run)
        assert run.status == RunStatus.COMPLETED

    def test_span_context_manager(self, tracer):
        run = tracer.start_run(
            agent_type="sql_agent", benchmark="sql_agent", task_id="t1"
        )
        with tracer.span(run, "llm_call", kind=SpanKind.LLM_CALL) as span:
            span.input_payload = {"prompt": "hello"}
            span.add_event("model_called")

        assert span.end_time is not None
        assert span.status == SpanStatus.OK

    def test_span_records_error(self, tracer):
        run = tracer.start_run(
            agent_type="sql_agent", benchmark="sql_agent", task_id="t1"
        )
        with pytest.raises(ValueError):
            with tracer.span(run, "bad_call") as span:
                raise ValueError("Test error")

        assert span.status == SpanStatus.ERROR
        assert "Test error" in span.error_message

    def test_policy_event_recording(self, tracer, storage):
        run = tracer.start_run(
            agent_type="sql_agent", benchmark="sql_agent", task_id="t1"
        )
        tracer.record_policy_event(
            run, None,
            policy_name="sql_policy",
            action="blocked",
            severity="high",
            reason="DROP table detected",
            tool_name="sql_execute",
        )
        events = storage.get_policy_events(run.run_id)
        assert len(events) == 1
        assert events[0]["action"] == "blocked"


class TestStorage:
    def test_save_and_retrieve_run(self, storage):
        run = Run(agent_type="sql_agent", benchmark="sql_agent", task_id="t1")
        span = run.start_span("test", kind=SpanKind.LLM_CALL)
        span.end()
        run.complete()

        storage.save_run(run)
        retrieved = storage.get_run(run.run_id)

        assert retrieved is not None
        assert retrieved.run_id == run.run_id
        assert retrieved.task_id == "t1"
        assert len(retrieved.spans) == 1

    def test_list_runs_filter(self, storage):
        for i in range(3):
            run = Run(agent_type="sql_agent", benchmark="sql_agent", task_id=f"t{i}")
            run.complete()
            storage.save_run(run)
        run2 = Run(agent_type="rag_agent", benchmark="enterprise_rag", task_id="rag-1")
        run2.complete()
        storage.save_run(run2)

        sql_runs = storage.list_runs(agent_type="sql_agent")
        assert len(sql_runs) == 3
        rag_runs = storage.list_runs(agent_type="rag_agent")
        assert len(rag_runs) == 1

    def test_count_runs(self, storage):
        assert storage.count_runs() == 0
        run = Run(agent_type="sql_agent", benchmark="sql_agent", task_id="t1")
        storage.save_run(run)
        assert storage.count_runs() == 1
