"""Evals router — trigger benchmark runs and retrieve results."""
from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Any

router = APIRouter()


class RunBenchmarkRequest(BaseModel):
    benchmark: str  # sql_agent | enterprise_rag | github_security
    task_ids: list[str] | None = None  # None = run all tasks
    model_provider: str = "mock"
    model_name: str = "mock"
    max_tasks: int = 10


@router.post("/benchmark")
async def trigger_benchmark(req: RunBenchmarkRequest, background_tasks: BackgroundTasks):
    """Trigger a benchmark run in the background."""
    job_id = __import__("uuid").uuid4().hex
    background_tasks.add_task(_run_benchmark, req, job_id)
    return {
        "job_id": job_id,
        "benchmark": req.benchmark,
        "status": "started",
        "message": f"Benchmark '{req.benchmark}' started — check /api/runs for results",
    }


async def _run_benchmark(req: RunBenchmarkRequest, job_id: str):
    """Background benchmark execution."""
    import sys, os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_benchmark_sync, req)


def _run_benchmark_sync(req: RunBenchmarkRequest):
    import sys, os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    if req.benchmark == "sql_agent":
        from benchmarks.sql_agent.run_benchmark import run as run_sql
        run_sql(
            max_tasks=req.max_tasks,
            model_provider=req.model_provider,
            task_ids=req.task_ids,
        )
    elif req.benchmark == "enterprise_rag":
        from benchmarks.enterprise_rag.run_benchmark import run as run_rag
        run_rag(
            max_tasks=req.max_tasks,
            model_provider=req.model_provider,
            task_ids=req.task_ids,
        )
    elif req.benchmark == "github_security":
        from benchmarks.github_security.run_benchmark import run as run_sec
        run_sec(
            max_tasks=req.max_tasks,
            model_provider=req.model_provider,
            task_ids=req.task_ids,
        )


@router.get("/results/{run_id}")
async def get_eval_result(run_id: str):
    """Get evaluation scores for a specific run."""
    from packages.tracing.storage import get_storage
    storage = get_storage()
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {
        "run_id": run_id,
        "task_id": run.task_id,
        "benchmark": run.benchmark,
        "eval_scores": run.eval_scores,
        "status": run.status.value if hasattr(run.status, "value") else run.status,
        "total_latency_ms": run.total_latency_ms,
        "policy_violations": run.policy_violations,
    }
