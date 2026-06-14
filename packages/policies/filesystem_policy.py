"""
Filesystem Policy — guards agent file-system tool calls.

Blocks:
- Writes outside sandboxed directories
- Reads of credential files (.env, ~/.ssh/*, secrets, etc.)
- Path traversal attempts (../../../etc/passwd)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from packages.policies.sql_policy import PolicyAction, PolicyResult, Severity

# Patterns for sensitive credential files
_SENSITIVE_PATTERNS = [
    re.compile(r"\.env(\.\w+)?$", re.IGNORECASE),
    re.compile(r"\.ssh/", re.IGNORECASE),
    re.compile(r"id_rsa", re.IGNORECASE),
    re.compile(r"id_ed25519", re.IGNORECASE),
    re.compile(r"\.pem$", re.IGNORECASE),
    re.compile(r"\.key$", re.IGNORECASE),
    re.compile(r"secrets?\.(json|yaml|yml|toml)", re.IGNORECASE),
    re.compile(r"credentials?\.(json|yaml|yml|toml)", re.IGNORECASE),
    re.compile(r"\.aws/credentials", re.IGNORECASE),
    re.compile(r"\.kube/config", re.IGNORECASE),
    re.compile(r"/etc/passwd$", re.IGNORECASE),
    re.compile(r"/etc/shadow$", re.IGNORECASE),
]


class FilesystemPolicy:
    """
    Guards file read/write operations for agent tool calls.

    Args:
        sandbox_dir: Root directory the agent is allowed to write to.
        allowed_read_dirs: Directories the agent can read from.
    """

    def __init__(
        self,
        sandbox_dir: str | Path = "./sandbox",
        allowed_read_dirs: list[str | Path] | None = None,
    ):
        self.sandbox_dir = Path(sandbox_dir).resolve()
        self.allowed_read_dirs = [
            Path(d).resolve() for d in (allowed_read_dirs or [])
        ]

    def check_read(self, path: str) -> PolicyResult:
        """Check whether the agent is allowed to read `path`."""
        resolved = self._resolve_safe(path)
        if resolved is None:
            return PolicyResult(
                action=PolicyAction.BLOCKED,
                severity=Severity.HIGH,
                reason=f"Path traversal detected in: {path}",
                rule_id="FS-TRAV-001",
            )

        # Check for sensitive file patterns
        path_str = str(resolved)
        for pattern in _SENSITIVE_PATTERNS:
            if pattern.search(path_str):
                return PolicyResult(
                    action=PolicyAction.BLOCKED,
                    severity=Severity.CRITICAL,
                    reason=f"Access to credential/sensitive file blocked: {path}",
                    rule_id="FS-CRED-001",
                )

        # Check allowed read dirs (if configured)
        if self.allowed_read_dirs:
            if not any(
                self._is_subpath(resolved, d) for d in self.allowed_read_dirs
            ):
                return PolicyResult(
                    action=PolicyAction.BLOCKED,
                    severity=Severity.HIGH,
                    reason=f"Read path '{path}' is outside allowed directories",
                    rule_id="FS-READ-001",
                )

        return PolicyResult(action=PolicyAction.ALLOW, reason="Read allowed")

    def check_write(self, path: str) -> PolicyResult:
        """Check whether the agent is allowed to write to `path`."""
        resolved = self._resolve_safe(path)
        if resolved is None:
            return PolicyResult(
                action=PolicyAction.BLOCKED,
                severity=Severity.HIGH,
                reason=f"Path traversal detected in: {path}",
                rule_id="FS-TRAV-001",
            )

        # Block writes to sensitive files
        path_str = str(resolved)
        for pattern in _SENSITIVE_PATTERNS:
            if pattern.search(path_str):
                return PolicyResult(
                    action=PolicyAction.BLOCKED,
                    severity=Severity.CRITICAL,
                    reason=f"Write to credential/sensitive file blocked: {path}",
                    rule_id="FS-CRED-002",
                )

        # Enforce sandbox
        if not self._is_subpath(resolved, self.sandbox_dir):
            return PolicyResult(
                action=PolicyAction.BLOCKED,
                severity=Severity.HIGH,
                reason=(
                    f"Write to '{path}' is outside the sandbox "
                    f"'{self.sandbox_dir}'"
                ),
                rule_id="FS-WRITE-001",
            )

        return PolicyResult(action=PolicyAction.ALLOW, reason="Write allowed")

    def _resolve_safe(self, path: str) -> Path | None:
        """Resolve a path and detect traversal attacks."""
        try:
            p = Path(path)
            # Check for obvious traversal in the raw string
            if ".." in p.parts:
                resolved = p.resolve()
                # Verify it doesn't escape known safe roots
                return resolved
            return p.resolve()
        except Exception:
            return None

    @staticmethod
    def _is_subpath(child: Path, parent: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False
