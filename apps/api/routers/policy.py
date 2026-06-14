"""Policy events router."""
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/events")
async def list_policy_events(
    run_id: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """List policy events across all runs."""
    from packages.tracing.storage import get_storage, policy_events_table
    from sqlalchemy import select, and_
    storage = get_storage()
    with storage._engine.connect() as conn:
        q = select(policy_events_table).order_by(
            policy_events_table.c.created_at.desc()
        )
        filters = []
        if run_id:
            filters.append(policy_events_table.c.run_id == run_id)
        if action:
            filters.append(policy_events_table.c.action == action)
        if filters:
            q = q.where(and_(*filters))
        q = q.limit(limit)
        rows = conn.execute(q).fetchall()
        events = []
        for r in rows:
            d = dict(r._mapping)
            if "created_at" in d and hasattr(d["created_at"], "isoformat"):
                d["created_at"] = d["created_at"].isoformat()
            events.append(d)
    return {"events": events, "total": len(events)}


@router.get("/summary/{run_id}")
async def policy_summary(run_id: str):
    """Get policy violation summary for a run."""
    from packages.tracing.storage import get_storage
    storage = get_storage()
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    events = storage.get_policy_events(run_id)
    by_action = {}
    by_policy = {}
    for e in events:
        a = e.get("action", "unknown")
        p = e.get("policy_name", "unknown")
        by_action[a] = by_action.get(a, 0) + 1
        by_policy[p] = by_policy.get(p, 0) + 1

    return {
        "run_id": run_id,
        "total_events": len(events),
        "by_action": by_action,
        "by_policy": by_policy,
        "hitl_required": run.hitl_required,
        "events": events,
    }
