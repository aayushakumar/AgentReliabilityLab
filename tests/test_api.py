"""
Integration tests for the FastAPI backend.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure root in path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test_api.db")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("HITL_ENABLED", "false")


@pytest.fixture(scope="module")
def client():
    """HTTP test client for FastAPI app."""
    # Reset engine singleton before starting
    import packages.tracing.storage as ts
    ts._engine = None
    ts._storage = None

    from fastapi.testclient import TestClient
    from apps.api.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def seed_test_data(client):
    """Seed a few runs so API tests have data to work with."""
    from packages.tracing.models import Run, RunStatus
    from packages.tracing.storage import get_storage

    storage = get_storage()
    for i in range(3):
        run = Run(
            agent_type="sql_agent",
            benchmark="sql_agent",
            task_id=f"sql-{i + 1:03d}",
            model_name="mock",
            model_provider="mock",
            status=RunStatus.RUNNING,
        )
        run.eval_scores = {"overall": 0.8, "sql_safety": 1.0}
        run.complete()
        storage.save_run(run)

    yield


class TestHealthEndpoints:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_stats(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        assert "total_runs" in resp.json()


class TestRunsAPI:
    def test_list_runs(self, client):
        resp = client.get("/api/runs/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 3

    def test_list_runs_filter_agent_type(self, client):
        resp = client.get("/api/runs/?agent_type=sql_agent")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(r["agent_type"] == "sql_agent" for r in items)

    def test_get_run_by_id(self, client):
        # Get first run ID from list
        runs = client.get("/api/runs/").json()["items"]
        assert len(runs) > 0
        run_id = runs[0]["run_id"]

        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id
        assert "spans" in data

    def test_get_run_not_found(self, client):
        resp = client.get("/api/runs/nonexistent-id")
        assert resp.status_code == 404

    def test_list_runs_pagination(self, client):
        resp = client.get("/api/runs/?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 2


class TestTracesAPI:
    def test_get_spans(self, client):
        runs = client.get("/api/runs/").json()["items"]
        run_id = runs[0]["run_id"]
        resp = client.get(f"/api/traces/{run_id}/spans")
        assert resp.status_code == 200
        data = resp.json()
        assert "spans" in data
        assert data["run_id"] == run_id

    def test_get_policy_events(self, client):
        runs = client.get("/api/runs/").json()["items"]
        run_id = runs[0]["run_id"]
        resp = client.get(f"/api/traces/{run_id}/policy-events")
        assert resp.status_code == 200
        assert "events" in resp.json()


class TestLeaderboardAPI:
    def test_leaderboard(self, client):
        resp = client.get("/api/leaderboard/")
        assert resp.status_code == 200
        assert "leaderboard" in resp.json()

    def test_leaderboard_filtered(self, client):
        resp = client.get("/api/leaderboard/?benchmark=sql_agent")
        assert resp.status_code == 200

    def test_aggregate_metrics(self, client):
        resp = client.get("/api/leaderboard/metrics")
        assert resp.status_code == 200
        assert "metric_averages" in resp.json()


class TestPolicyAPI:
    def test_policy_events_empty(self, client):
        resp = client.get("/api/policy/events")
        assert resp.status_code == 200
        assert "events" in resp.json()

    def test_policy_summary(self, client):
        runs = client.get("/api/runs/").json()["items"]
        run_id = runs[0]["run_id"]
        resp = client.get(f"/api/policy/summary/{run_id}")
        assert resp.status_code == 200


class TestHITLAPI:
    def test_list_pending(self, client):
        resp = client.get("/api/hitl/pending")
        assert resp.status_code == 200
        assert "checkpoints" in resp.json()

    def test_decide_nonexistent(self, client):
        resp = client.post(
            "/api/hitl/nonexistent/decide",
            json={"decision": "approve"},
        )
        assert resp.status_code == 404


class TestReplayAPI:
    def test_diff_nonexistent_runs(self, client):
        resp = client.get("/api/replay/diff/fake-a/fake-b")
        assert resp.status_code == 404

    def test_diff_same_run(self, client):
        runs = client.get("/api/runs/").json()["items"]
        if len(runs) >= 2:
            a = runs[0]["run_id"]
            b = runs[1]["run_id"]
            resp = client.get(f"/api/replay/diff/{a}/{b}")
            assert resp.status_code == 200
            assert "diffs" in resp.json()
