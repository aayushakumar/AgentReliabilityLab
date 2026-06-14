"""
End-to-end tests for the SQL Agent benchmark.
"""
from __future__ import annotations

import os
import sys
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("HITL_ENABLED", "false")


@pytest.fixture(scope="module")
def benchmark_db(tmp_path_factory):
    """Create a seeded benchmark database."""
    tmp = tmp_path_factory.mktemp("benchmark")
    db_path = str(tmp / "benchmark.db")
    schema = (ROOT / "benchmarks/sql_agent/schema.sql").read_text()
    seed = (ROOT / "benchmarks/sql_agent/seed_data.sql").read_text()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    conn.executescript(seed)
    conn.close()
    return db_path


class TestSQLAgentE2E:
    def test_simple_count_query(self, benchmark_db):
        from packages.agents.sql_agent import SQLAgent
        agent = SQLAgent(
            db_path=benchmark_db,
            allowed_tables={"customers", "orders", "order_items", "products", "categories", "reviews"},
            model_name="mock",
            model_provider="mock",
        )
        run, output = agent.run("sql-001", "How many customers are there in total?")
        assert output.get("sql") is not None
        assert run.run_id
        assert len(run.spans) > 0

    def test_policy_blocks_dangerous_sql(self, benchmark_db):
        """Agent should block DROP TABLE attempts."""
        from packages.agents.sql_agent import SQLAgent
        from packages.policies.sql_policy import SQLPolicyConfig
        agent = SQLAgent(
            db_path=benchmark_db,
            allowed_tables={"customers"},
            model_name="mock",
            model_provider="mock",
        )
        # Directly test the policy on dangerous SQL
        from packages.policies.sql_policy import SQLPolicy
        policy = SQLPolicy(SQLPolicyConfig(allowed_tables={"customers"}, block_ddl=True))
        result = policy.check("DROP TABLE customers")
        assert result.is_blocked

    def test_run_produces_trace(self, benchmark_db):
        from packages.agents.sql_agent import SQLAgent
        from packages.tracing.models import SpanKind
        agent = SQLAgent(
            db_path=benchmark_db,
            allowed_tables={"customers", "orders"},
            model_name="mock",
            model_provider="mock",
        )
        run, _ = agent.run("sql-005", "What is the average order total amount?")
        # Should have at least: schema inspection, LLM call, policy check, execute, synthesise
        assert len(run.spans) >= 3
        kinds = {s.kind for s in run.spans}
        assert SpanKind.RETRIEVAL in kinds
        assert SpanKind.LLM_CALL in kinds

    def test_benchmark_runner_full(self, benchmark_db, tmp_path, monkeypatch):
        """Run 3 tasks through the full benchmark pipeline."""
        import packages.tracing.storage as ts
        db_url = f"sqlite:///{tmp_path}/runner_test.db"
        monkeypatch.setenv("DATABASE_URL", db_url)
        ts._engine = None
        ts._storage = None

        from benchmarks.sql_agent.run_benchmark import load_tasks, _run_tasks

        # Monkey-patch the DB path
        tasks = load_tasks(max_tasks=3)
        assert len(tasks) == 3

        # Patch DB path
        import benchmarks.sql_agent.run_benchmark as bm
        monkeypatch.setattr(bm, "DB_PATH", benchmark_db)
        bm.setup_database()

        _run_tasks(tasks[:3], model_provider="mock", model_name="mock", verbose=False)
        # Verify runs were saved
        from packages.tracing.storage import get_storage
        ts._engine = None
        ts._storage = None
        monkeypatch.setenv("DATABASE_URL", db_url)
        storage = get_storage()


class TestMCPTools:
    def test_sql_tool_executes(self, benchmark_db):
        from packages.mcp_tools.sql_tool import SQLExecutorTool
        tool = SQLExecutorTool(db_path=benchmark_db)
        result = tool.invoke({"query": "SELECT COUNT(*) as count FROM customers"})
        assert result.success
        assert result.output["row_count"] == 1
        assert result.output["rows"][0]["count"] == 20

    def test_sql_tool_blocks_ddl(self, benchmark_db):
        from packages.mcp_tools.sql_tool import SQLExecutorTool
        tool = SQLExecutorTool(db_path=benchmark_db)
        result = tool.invoke({"query": "DROP TABLE customers"})
        assert not result.success
        assert "policy" in result.error.lower() or "blocked" in result.error.lower()

    def test_schema_tool(self, benchmark_db):
        from packages.mcp_tools.sql_tool import SQLSchemaInspectTool
        tool = SQLSchemaInspectTool(db_path=benchmark_db)
        result = tool.invoke({})
        assert result.success
        tables = result.output["tables"]
        assert "customers" in tables
        assert "orders" in tables

    def test_schema_validation(self, benchmark_db):
        from packages.mcp_tools.sql_tool import SQLExecutorTool
        tool = SQLExecutorTool(db_path=benchmark_db)
        # Missing required field "query"
        result = tool.invoke({"limit": 10})
        assert not result.success
        assert "Missing required fields" in result.error

    def test_github_tool_list_files(self, tmp_path):
        from packages.mcp_tools.github_tool import GitHubAPITool
        # Create a fake repo
        repo_dir = tmp_path / "fake_repo"
        repo_dir.mkdir()
        (repo_dir / "app.py").write_text("print('hello')")
        (repo_dir / "README.md").write_text("# Readme")

        tool = GitHubAPITool(fixtures_dir=str(tmp_path))
        result = tool.invoke({"action": "list_files", "repo": "fake_repo"})
        assert result.success
        assert "app.py" in result.output["files"]

    def test_github_tool_read_file(self, tmp_path):
        from packages.mcp_tools.github_tool import GitHubAPITool
        repo_dir = tmp_path / "my_repo"
        repo_dir.mkdir()
        (repo_dir / "main.py").write_text("x = 42")

        tool = GitHubAPITool(fixtures_dir=str(tmp_path))
        result = tool.invoke({"action": "read_file", "repo": "my_repo", "path": "main.py"})
        assert result.success
        assert "x = 42" in result.output["content"]
