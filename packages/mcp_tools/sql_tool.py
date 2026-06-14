"""
SQL Executor Tool — MCP-wrapped, policy-guarded SQL execution.
"""
from __future__ import annotations

import sqlite3
from typing import Any, ClassVar

from packages.mcp_tools.base import BaseTool, ToolSchema
from packages.policies.sql_policy import SQLPolicy, SQLPolicyConfig


class SQLExecutorTool(BaseTool):
    """
    Execute SQL queries against a sandboxed SQLite database.

    All queries are validated by the SQL policy engine before execution.
    """

    schema: ClassVar[ToolSchema] = ToolSchema(
        name="sql_execute",
        description=(
            "Execute a SQL SELECT query against the benchmark database. "
            "Only read queries are allowed; DDL and destructive DML are blocked."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The SQL query to execute (SELECT only).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return (default: 100).",
                    "default": 100,
                },
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "rows": {"type": "array"},
                "columns": {"type": "array"},
                "row_count": {"type": "integer"},
            },
        },
    )

    def __init__(
        self,
        db_path: str,
        sql_config: SQLPolicyConfig | None = None,
        policy_engine=None,
    ):
        super().__init__(policy_engine=policy_engine)
        self.db_path = db_path
        self._sql_policy = SQLPolicy(sql_config or SQLPolicyConfig(block_ddl=True))

    def _execute(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        query = input_dict["query"]
        limit = input_dict.get("limit", 100)

        # Policy check
        result = self._sql_policy.check(query)
        if not result.is_allowed:
            raise ValueError(f"SQL policy blocked query: {result.reason}")

        # Execute
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(query)
            rows = cursor.fetchmany(limit)
            columns = [desc[0] for desc in cursor.description or []]
            row_dicts = [dict(r) for r in rows]
            return {
                "rows": row_dicts,
                "columns": columns,
                "row_count": len(row_dicts),
            }
        finally:
            conn.close()


class SQLSchemaInspectTool(BaseTool):
    """Inspect the database schema — returns table names and column definitions."""

    schema: ClassVar[ToolSchema] = ToolSchema(
        name="sql_schema",
        description="Get the database schema: table names and their column definitions.",
        input_schema={
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Optional: specific table to inspect. Omit for all tables.",
                },
            },
        },
    )

    def __init__(self, db_path: str, policy_engine=None):
        super().__init__(policy_engine=policy_engine)
        self.db_path = db_path

    def _execute(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        table_name = input_dict.get("table_name")
        conn = sqlite3.connect(self.db_path)
        try:
            if table_name:
                cursor = conn.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                )
            else:
                cursor = conn.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            tables = {row[0]: row[1] for row in cursor.fetchall()}
            return {"tables": tables}
        finally:
            conn.close()
