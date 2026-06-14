"""HITL (Human-in-the-Loop) router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class HITLDecisionRequest(BaseModel):
    decision: str  # "approve" | "reject"
    decided_by: str = "human"


@router.get("/pending")
async def list_pending_checkpoints():
    """List all pending HITL checkpoints awaiting human decision."""
    from packages.policies.hitl import get_hitl_manager
    mgr = get_hitl_manager()
    checkpoints = mgr.list_pending()
    return {"checkpoints": [cp.to_dict() for cp in checkpoints]}


@router.get("/all")
async def list_all_checkpoints():
    """List all HITL checkpoints (pending + decided)."""
    from packages.policies.hitl import get_hitl_manager
    mgr = get_hitl_manager()
    checkpoints = mgr.list_all()
    return {"checkpoints": [cp.to_dict() for cp in checkpoints]}


@router.post("/{checkpoint_id}/decide")
async def decide_checkpoint(checkpoint_id: str, req: HITLDecisionRequest):
    """Approve or reject a HITL checkpoint."""
    from packages.policies.hitl import get_hitl_manager, HITLDecision
    mgr = get_hitl_manager()

    try:
        decision = HITLDecision(req.decision)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision '{req.decision}'. Must be 'approve' or 'reject'",
        )

    success = mgr.decide(checkpoint_id, decision, by=req.decided_by)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint '{checkpoint_id}' not found",
        )

    cp = mgr.get_checkpoint(checkpoint_id)
    return {
        "checkpoint_id": checkpoint_id,
        "decision": req.decision,
        "decided_by": req.decided_by,
        "checkpoint": cp.to_dict() if cp else None,
    }


@router.get("/{checkpoint_id}")
async def get_checkpoint(checkpoint_id: str):
    """Get details of a specific HITL checkpoint."""
    from packages.policies.hitl import get_hitl_manager
    mgr = get_hitl_manager()
    cp = mgr.get_checkpoint(checkpoint_id)
    if not cp:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint '{checkpoint_id}' not found",
        )
    return cp.to_dict()
