"""Runs router — CRUD for agent runs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Any

router = APIRouter()


class RunSummary(BaseModel):
    run_id: str
    agent_type: str
    benchmark: str
    task_id: str
    model_name: str
    framework: str
    status: str
    created_at: str
    completed_at: str | None
    total_steps: int
    total_tokens: int
    total_cost_usd: float
    total_latency_ms: float
    eval_scores: dict[str, float]
    policy_violations: list[dict]
    hitl_required: bool


def _run_to_summary(run) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "agent_type": run.agent_type,
        "benchmark": run.benchmark,
        "task_id": run.task_id,
        "model_name": run.model_name,
        "framework": run.framework,
        "status": run.status.value if hasattr(run.status, "value") else run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "total_steps": run.total_steps,
        "total_tokens": run.total_tokens,
        "total_cost_usd": round(run.total_cost_usd, 6),
        "total_latency_ms": round(run.total_latency_ms, 2),
        "eval_scores": run.eval_scores,
        "policy_violations": run.policy_violations,
        "hitl_required": run.hitl_required,
        "tags": run.tags,
    }


@router.get("/")
async def list_runs(
    agent_type: str | None = Query(None),
    benchmark: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List agent runs with optional filters."""
    from packages.tracing.storage import get_storage
    storage = get_storage()
    runs = storage.list_runs(
        agent_type=agent_type,
        benchmark=benchmark,
        status=status,
        limit=limit,
        offset=offset,
    )
    total = storage.count_runs()
    return {
        "items": [_run_to_summary(r) for r in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{run_id}")
async def get_run(run_id: str):
    """Get a specific run with all spans."""
    from packages.tracing.storage import get_storage
    storage = get_storage()
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    summary = _run_to_summary(run)
    summary["spans"] = [
        {
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "kind": s.kind.value if hasattr(s.kind, "value") else s.kind,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "end_time": s.end_time.isoformat() if s.end_time else None,
            "duration_ms": s.duration_ms,
            "input_payload": s.input_payload,
            "output_payload": s.output_payload,
            "status": s.status.value if hasattr(s.status, "value") else s.status,
            "error_message": s.error_message,
            "prompt_tokens": s.prompt_tokens,
            "completion_tokens": s.completion_tokens,
            "total_tokens": s.total_tokens,
        }
        for s in run.spans
    ]
    return summary


@router.delete("/{run_id}")
async def delete_run(run_id: str):
    """Delete a run and its spans."""
    from packages.tracing.storage import get_storage, runs_table, spans_table
    from sqlalchemy import delete
    storage = get_storage()
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    with storage._engine.begin() as conn:
        conn.execute(delete(spans_table).where(spans_table.c.run_id == run_id))
        conn.execute(delete(runs_table).where(runs_table.c.run_id == run_id))
    return {"deleted": run_id}
