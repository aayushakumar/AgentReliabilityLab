"""
Pytest configuration and shared fixtures.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on the Python path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Use an in-memory / temp SQLite for tests
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test_arl.db")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("HITL_ENABLED", "false")


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create the test database directory."""
    os.makedirs("data", exist_ok=True)
    yield
    # Cleanup happens naturally


@pytest.fixture
def temp_db(tmp_path):
    """A fresh SQLite database for each test."""
    db_path = str(tmp_path / "test.db")
    return db_path


@pytest.fixture
def sql_benchmark_db(tmp_path):
    """A seeded SQL benchmark database for grader tests."""
    import sqlite3
    db_path = str(tmp_path / "benchmark.db")
    schema = (ROOT / "benchmarks/sql_agent/schema.sql").read_text()
    seed = (ROOT / "benchmarks/sql_agent/seed_data.sql").read_text()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema)
    conn.executescript(seed)
    conn.close()
    return db_path


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Fresh TraceStorage backed by a temp SQLite file."""
    db_path = f"sqlite:///{tmp_path}/test_traces.db"
    monkeypatch.setenv("DATABASE_URL", db_path)

    # Reset singleton
    import packages.tracing.storage as ts
    ts._engine = None
    ts._storage = None

    from packages.tracing.storage import get_storage
    s = get_storage()
    yield s

    # Teardown
    ts._engine = None
    ts._storage = None


@pytest.fixture
def tracer(storage):
    """Fresh Tracer with the test storage."""
    import packages.tracing.tracer as tt
    tt._tracer = None
    from packages.tracing.tracer import Tracer
    t = Tracer(storage=storage)
    tt._tracer = t
    yield t
    tt._tracer = None


@pytest.fixture
def mock_llm():
    """The deterministic mock LLM."""
    from packages.agents.llm_provider import get_llm
    return get_llm(provider="mock")
