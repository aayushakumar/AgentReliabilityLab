"""
RBAC Policy — enforces role-based access control for RAG document retrieval.

Documents are tagged with a minimum clearance level; agents can only retrieve
documents at or below their configured clearance.

Also implements prompt-injection detection for retrieved content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from packages.policies.sql_policy import PolicyAction, PolicyResult, Severity

# Access levels (hierarchical — higher number = higher clearance)
CLEARANCE_LEVELS: dict[str, int] = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
    "top_secret": 4,
}

# Prompt injection signatures in retrieved documents
_INJECTION_SIGNATURES = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|my)", re.IGNORECASE),
    re.compile(r"new\s+instructions?:", re.IGNORECASE),
    re.compile(r"system\s+prompt\s*:", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all)", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
]


@dataclass
class DocumentMetadata:
    doc_id: str
    title: str
    clearance_level: str = "public"  # must be a key in CLEARANCE_LEVELS
    owner: str = "system"
    tags: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.clearance_level not in CLEARANCE_LEVELS:
            raise ValueError(
                f"Unknown clearance level: {self.clearance_level}. "
                f"Valid levels: {list(CLEARANCE_LEVELS.keys())}"
            )


class RBACPolicy:
    """
    Enforces document-level access control and prompt-injection detection.

    Args:
        agent_clearance: The clearance level granted to this agent instance.
    """

    def __init__(self, agent_clearance: str = "public"):
        if agent_clearance not in CLEARANCE_LEVELS:
            raise ValueError(f"Unknown agent clearance: {agent_clearance}")
        self.agent_clearance = agent_clearance
        self._agent_level = CLEARANCE_LEVELS[agent_clearance]

    def check_document_access(self, doc: DocumentMetadata) -> PolicyResult:
        """Determine if the agent can access this document."""
        doc_level = CLEARANCE_LEVELS.get(doc.clearance_level, 0)

        if doc_level > self._agent_level:
            return PolicyResult(
                action=PolicyAction.BLOCKED,
                severity=Severity.HIGH,
                reason=(
                    f"RBAC violation: document '{doc.doc_id}' requires "
                    f"'{doc.clearance_level}' clearance but agent has "
                    f"'{self.agent_clearance}'"
                ),
                rule_id="RBAC-001",
            )

        return PolicyResult(
            action=PolicyAction.ALLOW,
            reason=f"Agent clearance '{self.agent_clearance}' >= document level '{doc.clearance_level}'",
        )

    def check_content_injection(self, content: str) -> PolicyResult:
        """Scan document content for prompt-injection patterns."""
        for pattern in _INJECTION_SIGNATURES:
            m = pattern.search(content)
            if m:
                return PolicyResult(
                    action=PolicyAction.BLOCKED,
                    severity=Severity.CRITICAL,
                    reason=f"Prompt injection detected in document content: '{m.group()[:60]}'",
                    rule_id="RBAC-INJ-001",
                )
        return PolicyResult(action=PolicyAction.ALLOW, reason="No injection detected")

    def filter_documents(
        self, docs: list[tuple[DocumentMetadata, str]]
    ) -> tuple[list[tuple[DocumentMetadata, str]], list[PolicyResult]]:
        """
        Filter a list of (metadata, content) tuples.

        Returns:
            allowed: documents that pass all checks
            violations: list of PolicyResult for blocked documents
        """
        allowed = []
        violations = []

        for meta, content in docs:
            access_result = self.check_document_access(meta)
            if not access_result.is_allowed:
                violations.append(access_result)
                continue

            injection_result = self.check_content_injection(content)
            if not injection_result.is_allowed:
                violations.append(injection_result)
                continue

            allowed.append((meta, content))

        return allowed, violations
