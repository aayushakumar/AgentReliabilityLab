"""
Human-in-the-Loop (HITL) checkpoint manager.

When a tool call risk score exceeds the configured threshold, the agent
pauses and waits for human approval before proceeding.

In production this integrates with the dashboard's HITL API.
In tests/dev it can be configured to auto-approve or auto-reject.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class HITLDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    PENDING = "pending"
    TIMEOUT = "timeout"


class HITLCheckpoint:
    """A single pending human-approval request."""

    def __init__(
        self,
        run_id: str,
        span_id: str | None,
        tool_name: str,
        tool_input: dict[str, Any],
        risk_score: float,
        reason: str,
    ):
        self.checkpoint_id = uuid.uuid4().hex
        self.run_id = run_id
        self.span_id = span_id
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.risk_score = risk_score
        self.reason = reason
        self.decision = HITLDecision.PENDING
        self.decided_by: str | None = None
        self.decided_at: datetime | None = None
        self.created_at = datetime.now(timezone.utc)
        self._event = asyncio.Event()

    def approve(self, by: str = "human") -> None:
        self.decision = HITLDecision.APPROVE
        self.decided_by = by
        self.decided_at = datetime.now(timezone.utc)
        self._event.set()

    def reject(self, by: str = "human") -> None:
        self.decision = HITLDecision.REJECT
        self.decided_by = by
        self.decided_at = datetime.now(timezone.utc)
        self._event.set()

    async def wait(self, timeout_seconds: float = 300.0) -> HITLDecision:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            self.decision = HITLDecision.TIMEOUT
        return self.decision

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "run_id": self.run_id,
            "span_id": self.span_id,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "risk_score": self.risk_score,
            "reason": self.reason,
            "decision": self.decision.value,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "created_at": self.created_at.isoformat(),
        }


class HITLManager:
    """
    Manages HITL checkpoints in-memory.

    In production, integrate with the FastAPI HITL endpoints to persist
    checkpoints in the database and notify the dashboard via WebSocket.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        risk_threshold: float = 0.7,
        auto_approve: bool = False,  # useful in tests
        auto_reject: bool = False,
        timeout_seconds: float = 300.0,
    ):
        self.enabled = enabled
        self.risk_threshold = risk_threshold
        self.auto_approve = auto_approve
        self.auto_reject = auto_reject
        self.timeout_seconds = timeout_seconds

        self._checkpoints: dict[str, HITLCheckpoint] = {}
        self._on_checkpoint_callbacks: list[Callable[[HITLCheckpoint], Awaitable[None]]] = []

    def register_callback(
        self, cb: Callable[[HITLCheckpoint], Awaitable[None]]
    ) -> None:
        """Register a coroutine to call when a new checkpoint is created."""
        self._on_checkpoint_callbacks.append(cb)

    async def checkpoint(
        self,
        run_id: str,
        span_id: str | None,
        tool_name: str,
        tool_input: dict[str, Any],
        risk_score: float,
        reason: str,
    ) -> HITLDecision:
        """
        Create a checkpoint and wait for human decision.

        Returns the decision (APPROVE/REJECT/TIMEOUT).
        """
        if not self.enabled or risk_score < self.risk_threshold:
            return HITLDecision.APPROVE

        cp = HITLCheckpoint(
            run_id=run_id,
            span_id=span_id,
            tool_name=tool_name,
            tool_input=tool_input,
            risk_score=risk_score,
            reason=reason,
        )
        self._checkpoints[cp.checkpoint_id] = cp

        # Notify registered callbacks (e.g., push to WebSocket)
        for cb in self._on_checkpoint_callbacks:
            try:
                await cb(cp)
            except Exception:
                logger.exception("HITL callback failed")

        # Auto-approve/reject for non-interactive environments
        if self.auto_approve:
            cp.approve(by="auto")
            logger.info("HITL auto-approved checkpoint %s", cp.checkpoint_id)
            return HITLDecision.APPROVE

        if self.auto_reject:
            cp.reject(by="auto")
            logger.info("HITL auto-rejected checkpoint %s", cp.checkpoint_id)
            return HITLDecision.REJECT

        logger.info(
            "HITL checkpoint created: %s (tool=%s, risk=%.2f) — waiting for human",
            cp.checkpoint_id, tool_name, risk_score,
        )
        return await cp.wait(self.timeout_seconds)

    def get_checkpoint(self, checkpoint_id: str) -> HITLCheckpoint | None:
        return self._checkpoints.get(checkpoint_id)

    def list_pending(self) -> list[HITLCheckpoint]:
        return [
            cp for cp in self._checkpoints.values()
            if cp.decision == HITLDecision.PENDING
        ]

    def list_all(self) -> list[HITLCheckpoint]:
        return list(self._checkpoints.values())

    def decide(
        self,
        checkpoint_id: str,
        decision: HITLDecision,
        by: str = "human",
    ) -> bool:
        """Apply a human decision to a checkpoint."""
        cp = self._checkpoints.get(checkpoint_id)
        if not cp:
            return False
        if decision == HITLDecision.APPROVE:
            cp.approve(by=by)
        elif decision == HITLDecision.REJECT:
            cp.reject(by=by)
        return True


# Singleton HITL manager
_hitl_manager: HITLManager | None = None


def get_hitl_manager() -> HITLManager:
    global _hitl_manager
    if _hitl_manager is None:
        import os
        enabled = os.environ.get("HITL_ENABLED", "true").lower() == "true"
        threshold = float(os.environ.get("HITL_RISK_THRESHOLD", "0.7"))
        _hitl_manager = HITLManager(
            enabled=enabled,
            risk_threshold=threshold,
            auto_approve=not enabled,
        )
    return _hitl_manager
