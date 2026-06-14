"""
Policy Engine — orchestrates all policy checks for a tool call.

The engine assigns a risk score, runs the appropriate sub-policy,
and optionally routes to HITL before returning a final decision.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from packages.policies.sql_policy import SQLPolicy, SQLPolicyConfig, PolicyAction, PolicyResult, Severity
from packages.policies.filesystem_policy import FilesystemPolicy
from packages.policies.rbac_policy import RBACPolicy, DocumentMetadata
from packages.policies.hitl import HITLManager, HITLDecision, get_hitl_manager

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRequest:
    """A tool call intercepted by the policy engine."""
    tool_name: str
    tool_input: dict[str, Any]
    run_id: str
    span_id: str | None = None
    agent_clearance: str = "public"


@dataclass
class PolicyDecision:
    """Final decision returned by the engine to the agent."""
    allowed: bool
    action: PolicyAction
    reason: str
    rule_id: str = ""
    severity: str = Severity.LOW.value
    hitl_checkpoint_id: str | None = None
    risk_score: float = 0.0

    @classmethod
    def allow(cls, reason: str = "All checks passed") -> "PolicyDecision":
        return cls(allowed=True, action=PolicyAction.ALLOW, reason=reason)

    @classmethod
    def block(cls, reason: str, rule_id: str = "", severity: Severity = Severity.HIGH) -> "PolicyDecision":
        return cls(
            allowed=False,
            action=PolicyAction.BLOCKED,
            reason=reason,
            rule_id=rule_id,
            severity=severity.value,
        )


class PolicyEngine:
    """
    Central policy engine.

    Intercepts every tool call, runs applicable policies,
    computes a risk score, and optionally routes to HITL.
    """

    def __init__(
        self,
        *,
        sql_config: SQLPolicyConfig | None = None,
        sandbox_dir: str = "./sandbox",
        allowed_read_dirs: list[str] | None = None,
        hitl_manager: HITLManager | None = None,
    ):
        self._sql_policy = SQLPolicy(sql_config)
        self._fs_policy = FilesystemPolicy(
            sandbox_dir=sandbox_dir,
            allowed_read_dirs=allowed_read_dirs or [],
        )
        self._hitl = hitl_manager or get_hitl_manager()

    def evaluate_sync(self, request: ToolCallRequest) -> PolicyDecision:
        """
        Synchronous evaluation (no HITL wait).

        Useful in deterministic benchmarks where HITL is disabled.
        """
        result = self._run_policies(request)
        if not result.is_allowed:
            return PolicyDecision.block(
                result.reason,
                rule_id=result.rule_id,
                severity=Severity(result.severity),
            )
        risk = self._compute_risk(request)
        if risk >= self._hitl.risk_threshold and self._hitl.enabled:
            return PolicyDecision(
                allowed=False,
                action=PolicyAction.HITL,
                reason=f"High-risk tool call (score={risk:.2f}) routed to HITL",
                risk_score=risk,
                severity=Severity.HIGH.value,
            )
        return PolicyDecision.allow()

    async def evaluate(self, request: ToolCallRequest) -> PolicyDecision:
        """
        Async evaluation with optional HITL wait.
        """
        result = self._run_policies(request)
        if not result.is_allowed:
            return PolicyDecision.block(
                result.reason,
                rule_id=result.rule_id,
                severity=Severity(result.severity),
            )

        risk = self._compute_risk(request)
        if risk >= self._hitl.risk_threshold and self._hitl.enabled:
            decision = await self._hitl.checkpoint(
                run_id=request.run_id,
                span_id=request.span_id,
                tool_name=request.tool_name,
                tool_input=request.tool_input,
                risk_score=risk,
                reason=f"High-risk tool call: {request.tool_name}",
            )
            if decision != HITLDecision.APPROVE:
                return PolicyDecision.block(
                    f"HITL rejected tool call '{request.tool_name}'",
                    severity=Severity.HIGH,
                )
            return PolicyDecision.allow(reason="HITL approved")

        return PolicyDecision.allow()

    # ─────────────────────────── Internal ─────────────────────────────

    def _run_policies(self, request: ToolCallRequest) -> PolicyResult:
        """Run the applicable sub-policy for this tool type."""
        tool = request.tool_name
        inp = request.tool_input

        if tool == "sql_execute":
            sql = inp.get("query") or inp.get("sql", "")
            return self._sql_policy.check(sql)

        if tool == "file_read":
            from packages.policies.filesystem_policy import FilesystemPolicy
            return self._fs_policy.check_read(inp.get("path", ""))

        if tool == "file_write":
            return self._fs_policy.check_write(inp.get("path", ""))

        # Default: allowed (unknown tools pass through with risk scoring)
        return PolicyResult(action=PolicyAction.ALLOW, reason="Unknown tool type — allowed by default")

    def _compute_risk(self, request: ToolCallRequest) -> float:
        """
        Heuristic risk score in [0, 1] for a tool call.

        Used to decide whether to route to HITL.
        """
        tool = request.tool_name
        inp = request.tool_input

        # Base risk by tool type
        base: dict[str, float] = {
            "sql_execute": 0.4,
            "file_write": 0.6,
            "file_read": 0.2,
            "web_search": 0.1,
            "github_api": 0.5,
        }
        risk = base.get(tool, 0.3)

        # Elevate for destructive SQL patterns
        if tool == "sql_execute":
            sql = (inp.get("query") or inp.get("sql", "")).upper()
            if any(kw in sql for kw in ["DELETE", "UPDATE", "INSERT", "DROP"]):
                risk += 0.3
            if "WHERE" not in sql and any(kw in sql for kw in ["DELETE", "UPDATE"]):
                risk = 0.95  # Almost certainly dangerous

        # Elevate for writes outside sandbox
        if tool == "file_write" and ".." in inp.get("path", ""):
            risk = 0.99

        return min(risk, 1.0)


# ─────────────────────────── Singleton ────────────────────────────────────

_engine: PolicyEngine | None = None


def get_policy_engine(sql_config: SQLPolicyConfig | None = None) -> PolicyEngine:
    global _engine
    if _engine is None:
        import os
        sandbox = os.environ.get("SANDBOX_DIR", "./sandbox")
        _engine = PolicyEngine(sql_config=sql_config, sandbox_dir=sandbox)
    return _engine
