"""
SQL Agent — LangGraph ReAct agent with policy-guarded SQL tool.

Architecture:
  planner → tool_call → policy_check → sql_execute → result_parser → answer
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from packages.agents.llm_provider import get_llm
from packages.mcp_tools.sql_tool import SQLExecutorTool, SQLSchemaInspectTool
from packages.policies.sql_policy import SQLPolicyConfig
from packages.tracing.models import Run, RunStatus, SpanKind
from packages.tracing.tracer import get_tracer

logger = logging.getLogger(__name__)

SQL_SYSTEM_PROMPT = """\
You are an expert data analyst. You have access to a SQL database.
Use the sql_schema tool first to understand the schema, then use sql_execute to answer the question.

Rules:
- ONLY write SELECT queries — no INSERT, UPDATE, DELETE, or DDL.
- Always include a LIMIT clause (max 100 rows) unless counting.
- Reference only tables and columns that exist in the schema.
- Return a clear, concise answer after executing the query.

When you have the final answer, respond with:
FINAL ANSWER: <your answer here>
"""


class SQLAgent:
    """
    LangGraph-based SQL agent with full tracing and policy enforcement.

    The agent:
    1. Inspects the schema (traced as RETRIEVAL span)
    2. Generates SQL (traced as LLM_CALL span)
    3. Validates SQL via policy (traced as POLICY_CHECK span)
    4. Executes query (traced as TOOL_CALL span)
    5. Synthesises an answer (traced as LLM_CALL span)
    """

    def __init__(
        self,
        db_path: str,
        *,
        llm=None,
        allowed_tables: set[str] | None = None,
        max_retries: int = 3,
        model_name: str | None = None,
        model_provider: str | None = None,
    ):
        self.db_path = db_path
        self.max_retries = max_retries
        self.model_name = model_name or os.environ.get("OLLAMA_MODEL", "mock")
        self.model_provider = model_provider or os.environ.get("LLM_PROVIDER", "mock")

        self._llm = llm or get_llm()
        self._schema_tool = SQLSchemaInspectTool(db_path)

        sql_config = SQLPolicyConfig(
            allowed_tables=allowed_tables or set(),
            enforce_allowlist=bool(allowed_tables),
            block_ddl=True,
        )
        self._sql_tool = SQLExecutorTool(db_path, sql_config=sql_config)
        self._tracer = get_tracer()
        self._allowed_tables = allowed_tables

    def run(self, task_id: str, question: str) -> tuple[Run, dict[str, Any]]:
        """
        Execute the SQL agent for a single benchmark task.

        Returns (Run with full trace, output dict with sql/rows/answer).
        """
        run = self._tracer.start_run(
            agent_type="sql_agent",
            benchmark="sql_agent",
            task_id=task_id,
            model_name=self.model_name,
            model_provider=self.model_provider,
            framework="langgraph",
        )

        output: dict[str, Any] = {
            "question": question,
            "sql": None,
            "rows": [],
            "answer": "",
            "retries": 0,
            "policy_blocked": False,
        }

        try:
            # Step 1: Inspect schema
            schema_info = self._inspect_schema(run)

            # Step 2: Generate + execute SQL (with retries)
            sql, rows, answer = self._generate_and_execute(
                run, question, schema_info, output
            )
            output["sql"] = sql
            output["rows"] = rows
            output["answer"] = answer

            run.eval_scores = {}
            self._tracer.finish_run(run, RunStatus.COMPLETED)

        except Exception as e:
            logger.exception("SQL agent failed for task %s", task_id)
            output["error"] = str(e)
            self._tracer.finish_run(run, RunStatus.FAILED)

        return run, output

    def _inspect_schema(self, run: Run) -> str:
        """Fetch and return schema as a formatted string."""
        with self._tracer.span(
            run, "schema_inspection", kind=SpanKind.RETRIEVAL
        ) as span:
            result = self._schema_tool.invoke({})
            if not result.success:
                raise RuntimeError(f"Schema inspection failed: {result.error}")
            tables = result.output.get("tables", {})
            schema_text = "\n".join(
                f"Table: {name}\n{sql}" for name, sql in tables.items()
            )
            span.output_payload = {"table_count": len(tables)}
        return schema_text

    def _generate_and_execute(
        self,
        run: Run,
        question: str,
        schema_info: str,
        output: dict,
    ) -> tuple[str, list[dict], str]:
        """Generate SQL, validate via policy, execute, synthesise answer."""
        from packages.policies.engine import PolicyEngine, ToolCallRequest
        from packages.policies.sql_policy import SQLPolicy, SQLPolicyConfig

        policy = PolicyEngine(
            sql_config=SQLPolicyConfig(
                allowed_tables=self._allowed_tables or set(),
                enforce_allowlist=bool(self._allowed_tables),
                block_ddl=True,
            )
        )

        last_error = ""
        for attempt in range(self.max_retries):
            # Generate SQL
            prompt = self._build_prompt(question, schema_info, last_error)

            with self._tracer.span(
                run, f"llm_generate_sql_attempt_{attempt + 1}", kind=SpanKind.LLM_CALL,
                input_payload={"question": question, "attempt": attempt + 1}
            ) as llm_span:
                response = self._llm.invoke(prompt)
                sql = self._extract_sql(
                    response.content if hasattr(response, "content") else str(response)
                )
                llm_span.output_payload = {"sql": sql}

            if not sql:
                last_error = "Could not extract SQL from LLM response"
                output["retries"] += 1
                continue

            # Policy check
            with self._tracer.span(
                run, "policy_check_sql", kind=SpanKind.POLICY_CHECK,
                input_payload={"sql": sql}
            ) as policy_span:
                req = ToolCallRequest(
                    tool_name="sql_execute",
                    tool_input={"query": sql},
                    run_id=run.run_id,
                    span_id=policy_span.span_id,
                )
                decision = policy.evaluate_sync(req)
                policy_span.output_payload = {
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                }

            if not decision.allowed:
                output["policy_blocked"] = True
                self._tracer.record_policy_event(
                    run, policy_span,
                    policy_name="sql_policy",
                    action="blocked",
                    severity="high",
                    reason=decision.reason,
                    tool_name="sql_execute",
                    tool_input={"query": sql},
                )
                last_error = f"SQL blocked by policy: {decision.reason}"
                output["retries"] += 1
                continue

            # Execute SQL
            with self._tracer.span(
                run, "sql_execute", kind=SpanKind.TOOL_CALL,
                input_payload={"sql": sql}
            ) as exec_span:
                tool_result = self._sql_tool.invoke({"query": sql, "limit": 100})
                if not tool_result.success:
                    exec_span.end(status="error", error=tool_result.error)  # type: ignore[arg-type]
                    last_error = f"SQL execution error: {tool_result.error}"
                    output["retries"] += 1
                    continue
                rows = tool_result.output.get("rows", [])
                exec_span.output_payload = {
                    "row_count": len(rows),
                    "columns": tool_result.output.get("columns", []),
                }

            # Synthesise answer
            answer = self._synthesise_answer(run, question, sql, rows)
            return sql, rows, answer

        # All retries exhausted
        return "", [], f"Failed after {self.max_retries} attempts. Last error: {last_error}"

    def _synthesise_answer(
        self, run: Run, question: str, sql: str, rows: list[dict]
    ) -> str:
        rows_text = json.dumps(rows[:10], indent=2) if rows else "No rows returned"
        prompt = f"""
Question: {question}
SQL executed: {sql}
Results (first 10 rows): {rows_text}

Provide a concise, direct answer to the question based on these results.
"""
        with self._tracer.span(run, "llm_synthesise_answer", kind=SpanKind.FINAL_ANSWER,
                               input_payload={"rows_preview": rows[:3]}) as span:
            response = self._llm.invoke(prompt)
            answer = response.content if hasattr(response, "content") else str(response)
            # Strip "FINAL ANSWER:" prefix if present
            answer = re.sub(r"^FINAL ANSWER:\s*", "", answer, flags=re.IGNORECASE).strip()
            span.output_payload = {"answer": answer[:200]}
        return answer

    def _build_prompt(self, question: str, schema: str, last_error: str) -> str:
        error_note = f"\n\nPrevious attempt failed: {last_error}\nPlease fix the SQL." if last_error else ""
        return f"""{SQL_SYSTEM_PROMPT}

Database Schema:
{schema}

Question: {question}{error_note}

Write a single SQL query to answer this question. Output ONLY the SQL query, no explanation."""

    @staticmethod
    def _extract_sql(text: str) -> str:
        """Extract SQL from LLM response — handles code blocks and raw SQL."""
        # Try to find SQL in code block
        code_block = re.search(r"```(?:sql)?\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if code_block:
            return code_block.group(1).strip()

        # Look for SELECT / WITH statements
        sql_match = re.search(
            r"((?:SELECT|WITH|INSERT|UPDATE|DELETE)\b.*?)(?:;|\Z)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if sql_match:
            return sql_match.group(1).strip()

        # If the entire response looks like SQL
        stripped = text.strip()
        if stripped.upper().startswith(("SELECT", "WITH")):
            return stripped

        return ""
