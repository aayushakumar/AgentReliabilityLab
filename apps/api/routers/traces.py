"""Traces router — span-level trace viewer."""
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/{run_id}/spans")
async def get_spans(run_id: str):
    """Get all spans for a run (timeline view)."""
    from packages.tracing.storage import get_storage
    storage = get_storage()
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    spans = []
    for s in run.spans:
        spans.append({
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "kind": s.kind.value if hasattr(s.kind, "value") else s.kind,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "end_time": s.end_time.isoformat() if s.end_time else None,
            "duration_ms": round(s.duration_ms or 0, 2),
            "input_payload": s.input_payload,
            "output_payload": s.output_payload,
            "attributes": s.attributes,
            "events": [e.model_dump(mode="json") for e in s.events],
            "status": s.status.value if hasattr(s.status, "value") else s.status,
            "error_message": s.error_message,
            "prompt_tokens": s.prompt_tokens,
            "completion_tokens": s.completion_tokens,
            "total_tokens": s.total_tokens,
            "estimated_cost_usd": s.estimated_cost_usd,
        })

    return {"run_id": run_id, "trace_id": run.trace_id, "spans": spans}


@router.get("/{run_id}/policy-events")
async def get_policy_events(run_id: str):
    """Get all policy events for a run."""
    from packages.tracing.storage import get_storage
    storage = get_storage()
    events = storage.get_policy_events(run_id)
    # Serialize datetime fields
    for e in events:
        if "created_at" in e and hasattr(e["created_at"], "isoformat"):
            e["created_at"] = e["created_at"].isoformat()
    return {"run_id": run_id, "events": events}
