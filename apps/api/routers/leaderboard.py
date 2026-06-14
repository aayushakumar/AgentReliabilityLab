"""Leaderboard router."""
from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/")
async def leaderboard(benchmark: str | None = Query(None)):
    """Get aggregated benchmark leaderboard."""
    from packages.tracing.storage import get_storage
    storage = get_storage()
    rows = storage.leaderboard(benchmark=benchmark)

    # Compute task_success_rate per group
    enriched = []
    for row in rows:
        r = dict(row)
        r["avg_latency_ms"] = round(r.get("avg_latency_ms") or 0, 2)
        r["avg_tokens"] = round(r.get("avg_tokens") or 0, 1)
        r["avg_cost_usd"] = round(r.get("avg_cost_usd") or 0, 6)
        enriched.append(r)

    return {"leaderboard": enriched, "benchmark": benchmark}


@router.get("/metrics")
async def aggregate_metrics(benchmark: str | None = Query(None)):
    """Aggregate eval scores across completed runs."""
    from packages.tracing.storage import get_storage, runs_table
    from sqlalchemy import select
    import json

    storage = get_storage()
    with storage._engine.connect() as conn:
        q = select(runs_table.c.eval_scores, runs_table.c.benchmark).where(
            runs_table.c.status == "completed"
        )
        if benchmark:
            q = q.where(runs_table.c.benchmark == benchmark)
        rows = conn.execute(q).fetchall()

    all_scores: dict[str, list[float]] = {}
    for row in rows:
        scores = json.loads(row[0] or "{}")
        for k, v in scores.items():
            if isinstance(v, (int, float)):
                all_scores.setdefault(k, []).append(float(v))

    averages = {k: round(sum(v) / len(v), 4) for k, v in all_scores.items() if v}
    return {"benchmark": benchmark, "metric_averages": averages, "run_count": len(rows)}
