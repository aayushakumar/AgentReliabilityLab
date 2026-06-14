"""
SQL Policy — validates SQL queries using AST analysis.

Uses sqlglot for robust, dialect-aware SQL parsing.
Blocks: DROP, DELETE without WHERE, raw exec(), non-allowlisted tables, etc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import sqlglot
import sqlglot.expressions as exp


class PolicyAction(str, Enum):
    ALLOW = "allow"
    BLOCKED = "blocked"
    WARN = "warn"
    HITL = "hitl"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PolicyResult:
    action: PolicyAction
    severity: Severity = Severity.LOW
    reason: str = ""
    rule_id: str = ""
    sanitized_sql: Optional[str] = None

    @property
    def is_allowed(self) -> bool:
        return self.action == PolicyAction.ALLOW

    @property
    def is_blocked(self) -> bool:
        return self.action == PolicyAction.BLOCKED


@dataclass
class SQLPolicyConfig:
    """Configuration for the SQL policy engine."""
    # Tables the agent is allowed to read from
    allowed_tables: set[str] = field(default_factory=set)
    # Tables the agent can write to (subset of allowed_tables).
    # None = no write restriction. Empty set = no writes allowed.
    writable_tables: set[str] | None = None
    # Enforce that DELETE must have a WHERE clause
    require_where_on_delete: bool = True
    # Block DDL statements entirely
    block_ddl: bool = True
    # Block TRUNCATE
    block_truncate: bool = True
    # Block raw exec() / system calls embedded in SQL
    block_exec: bool = True
    # Block multiple statements in one call
    block_multiple_statements: bool = True
    # If True, any table not in allowed_tables is blocked
    enforce_allowlist: bool = True
    # Max complexity (number of AST nodes) — prevent DoS
    max_ast_nodes: int = 500


# Dangerous SQL keywords that signal injection attempts
_INJECTION_PATTERNS = [
    re.compile(r";\s*(drop|alter|create|truncate|insert|update|delete)\s", re.IGNORECASE),
    re.compile(r"exec\s*\(", re.IGNORECASE),
    re.compile(r"xp_cmdshell", re.IGNORECASE),
    re.compile(r"INFORMATION_SCHEMA\.", re.IGNORECASE),
    re.compile(r"--\s", re.IGNORECASE),
    re.compile(r"/\*.*?\*/", re.IGNORECASE | re.DOTALL),
]


class SQLPolicy:
    """
    AST-based SQL policy engine.

    Example:
        policy = SQLPolicy(SQLPolicyConfig(
            allowed_tables={"orders", "products", "customers"},
        ))
        result = policy.check("SELECT * FROM orders WHERE id = 1")
        assert result.is_allowed
    """

    def __init__(self, config: SQLPolicyConfig | None = None):
        self.config = config or SQLPolicyConfig()

    def check(self, sql: str, dialect: str = "sqlite") -> PolicyResult:
        """
        Parse and evaluate SQL against all configured rules.
        Returns PolicyResult — caller decides whether to execute.
        """
        if not sql or not sql.strip():
            return PolicyResult(
                action=PolicyAction.BLOCKED,
                severity=Severity.MEDIUM,
                reason="Empty SQL statement",
                rule_id="SQL-001",
            )

        # Injection pattern check (fast path, no parse needed)
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(sql):
                return PolicyResult(
                    action=PolicyAction.BLOCKED,
                    severity=Severity.CRITICAL,
                    reason=f"SQL injection pattern detected: {pattern.pattern[:40]}",
                    rule_id="SQL-INJ-001",
                )

        # Parse AST
        try:
            statements = list(sqlglot.parse(sql, dialect=dialect, error_level=sqlglot.ErrorLevel.RAISE))
        except sqlglot.errors.ParseError as e:
            return PolicyResult(
                action=PolicyAction.BLOCKED,
                severity=Severity.HIGH,
                reason=f"SQL parse error: {e}",
                rule_id="SQL-PARSE-001",
            )

        # Multiple statement check
        if self.config.block_multiple_statements and len(statements) > 1:
            return PolicyResult(
                action=PolicyAction.BLOCKED,
                severity=Severity.HIGH,
                reason=f"Multiple statements ({len(statements)}) in a single call are not allowed",
                rule_id="SQL-002",
            )

        # Evaluate each statement
        for stmt in statements:
            if stmt is None:
                continue
            result = self._check_statement(stmt)
            if not result.is_allowed:
                return result

        return PolicyResult(action=PolicyAction.ALLOW, reason="All checks passed")

    def _check_statement(self, stmt: exp.Expression) -> PolicyResult:
        """Evaluate a single parsed statement."""
        node_count = sum(1 for _ in stmt.walk())
        if node_count > self.config.max_ast_nodes:
            return PolicyResult(
                action=PolicyAction.BLOCKED,
                severity=Severity.HIGH,
                reason=f"Query complexity ({node_count} nodes) exceeds limit ({self.config.max_ast_nodes})",
                rule_id="SQL-COMPLEX-001",
            )

        # DDL checks
        if self.config.block_ddl:
            ddl_types = (
                exp.Drop, exp.Create, exp.Alter,
                exp.AlterRename, exp.AlterColumn, exp.DropPartition,
            )
            if isinstance(stmt, ddl_types):
                return PolicyResult(
                    action=PolicyAction.BLOCKED,
                    severity=Severity.CRITICAL,
                    reason=f"DDL statement '{type(stmt).__name__}' is not allowed",
                    rule_id="SQL-DDL-001",
                )

        # TRUNCATE check
        if self.config.block_truncate and isinstance(stmt, exp.TruncateTable):
            return PolicyResult(
                action=PolicyAction.BLOCKED,
                severity=Severity.CRITICAL,
                reason="TRUNCATE is not allowed",
                rule_id="SQL-DDL-002",
            )

        # DELETE without WHERE check
        if isinstance(stmt, exp.Delete) and self.config.require_where_on_delete:
            if not stmt.find(exp.Where):
                return PolicyResult(
                    action=PolicyAction.BLOCKED,
                    severity=Severity.HIGH,
                    reason="DELETE without WHERE clause blocks all rows — not allowed",
                    rule_id="SQL-DML-001",
                )

        # Table allowlist
        if self.config.enforce_allowlist and self.config.allowed_tables:
            tables = self._extract_tables(stmt)
            for table in tables:
                if table.lower() not in {t.lower() for t in self.config.allowed_tables}:
                    return PolicyResult(
                        action=PolicyAction.BLOCKED,
                        severity=Severity.HIGH,
                        reason=f"Table '{table}' is not in the allowlist",
                        rule_id="SQL-TABLE-001",
                    )

        # Write to non-writable table check
        # writable_tables=None means "no restriction"; empty set means "no writes"
        if self.config.writable_tables is not None:
            if isinstance(stmt, (exp.Insert, exp.Update, exp.Delete)):
                tables = self._extract_tables(stmt)
                for table in tables:
                    if table.lower() not in {t.lower() for t in self.config.writable_tables}:
                        return PolicyResult(
                            action=PolicyAction.BLOCKED,
                            severity=Severity.HIGH,
                            reason=f"Write to non-writable table '{table}' is not allowed",
                            rule_id="SQL-TABLE-002",
                        )

        return PolicyResult(action=PolicyAction.ALLOW, reason="Statement passed all checks")

    def _extract_tables(self, stmt: exp.Expression) -> list[str]:
        """Extract all referenced table names from an AST node."""
        tables = []
        for node in stmt.walk():
            if isinstance(node, exp.Table) and node.name:
                tables.append(node.name)
        return list(set(tables))


def check_sql_safety(sql: str, allowed_tables: set[str] | None = None) -> PolicyResult:
    """Convenience function for one-off SQL checks."""
    cfg = SQLPolicyConfig(
        allowed_tables=allowed_tables or set(),
        enforce_allowlist=bool(allowed_tables),
    )
    return SQLPolicy(cfg).check(sql)
