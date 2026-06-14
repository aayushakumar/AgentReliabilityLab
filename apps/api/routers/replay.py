"""Trace Replay router — re-run failed traces with modified config."""
from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Any

router = APIRouter()


class ReplayRequest(BaseModel):
    """Configuration override for replaying a run."""
    run_id: str
    model_provider: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    sql_policy_strict: bool | None = None
    hitl_enabled: bool | None = None
    k_retrieval: int | None = None


class ReplayDiff(BaseModel):
    original_run_id: str
    replayed_run_id: str
    diffs: list[dict[str, Any]]


@router.post("/")
async def replay_run(req: ReplayRequest, background_tasks: BackgroundTasks):
    """Re-run a stored trace with modified configuration."""
    from packages.tracing.storage import get_storage
    storage = get_storage()
    original = storage.get_run(req.run_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"Run '{req.run_id}' not found")

    job_id = __import__("uuid").uuid4().hex
    background_tasks.add_task(_replay_task, req, original, job_id)
    return {
        "job_id": job_id,
        "original_run_id": req.run_id,
        "status": "started",
        "config": req.model_dump(exclude_none=True),
    }


async def _replay_task(req: ReplayRequest, original, job_id: str):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _replay_sync, req, original)


def _replay_sync(req, original):
    """Synchronously replay the run."""
    import sys, os
    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    )
    if root not in sys.path:
        sys.path.insert(0, root)

    benchmark = original.benchmark
    task_id = original.task_id
    provider = req.model_provider or original.model_provider
    model = req.model_name or original.model_name

    if benchmark == "sql_agent":
        from benchmarks.sql_agent.run_benchmark import run_single_task
        run_single_task(task_id=task_id, model_provider=provider, model_name=model)
    elif benchmark == "enterprise_rag":
        from benchmarks.enterprise_rag.run_benchmark import run_single_task
        run_single_task(task_id=task_id, model_provider=provider, model_name=model)
    elif benchmark == "github_security":
        from benchmarks.github_security.run_benchmark import run_single_task
        run_single_task(task_id=task_id, model_provider=provider, model_name=model)


@router.get("/diff/{run_id_a}/{run_id_b}")
async def diff_runs(run_id_a: str, run_id_b: str):
    """Compare two runs — show differences in spans, scores, and tool calls."""
    from packages.tracing.storage import get_storage
    storage = get_storage()

    run_a = storage.get_run(run_id_a)
    run_b = storage.get_run(run_id_b)
    if not run_a:
        raise HTTPException(status_code=404, detail=f"Run '{run_id_a}' not found")
    if not run_b:
        raise HTTPException(status_code=404, detail=f"Run '{run_id_b}' not found")

    diffs = []

    # Score diffs
    all_metrics = set(run_a.eval_scores) | set(run_b.eval_scores)
    for metric in sorted(all_metrics):
        a_val = run_a.eval_scores.get(metric)
        b_val = run_b.eval_scores.get(metric)
        if a_val != b_val:
            diffs.append({
                "type": "score",
                "metric": metric,
                "run_a": a_val,
                "run_b": b_val,
                "delta": (b_val or 0) - (a_val or 0),
            })

    # Latency diff
    if abs(run_a.total_latency_ms - run_b.total_latency_ms) > 50:
        diffs.append({
            "type": "latency",
            "run_a": run_a.total_latency_ms,
            "run_b": run_b.total_latency_ms,
            "delta": run_b.total_latency_ms - run_a.total_latency_ms,
        })

    # Policy violations diff
    if len(run_a.policy_violations) != len(run_b.policy_violations):
        diffs.append({
            "type": "policy_violations",
            "run_a": len(run_a.policy_violations),
            "run_b": len(run_b.policy_violations),
        })

    # Step count diff
    if run_a.total_steps != run_b.total_steps:
        diffs.append({
            "type": "steps",
            "run_a": run_a.total_steps,
            "run_b": run_b.total_steps,
        })

    return {
        "run_id_a": run_id_a,
        "run_id_b": run_id_b,
        "diffs": diffs,
        "summary": {
            "run_a": {
                "model": run_a.model_name,
                "status": run_a.status.value if hasattr(run_a.status, "value") else run_a.status,
                "latency_ms": run_a.total_latency_ms,
                "eval_scores": run_a.eval_scores,
            },
            "run_b": {
                "model": run_b.model_name,
                "status": run_b.status.value if hasattr(run_b.status, "value") else run_b.status,
                "latency_ms": run_b.total_latency_ms,
                "eval_scores": run_b.eval_scores,
            },
        },
    }
