#!/usr/bin/env python3
"""
Seed all benchmark databases and pre-populate test data.
Run: python scripts/seed_databases.py
"""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.makedirs("data", exist_ok=True)

def main():
    print("Seeding SQL Agent benchmark database…")
    from benchmarks.sql_agent.run_benchmark import setup_database
    setup_database()
    print("✓ SQL benchmark DB ready")

    print("\nGenerating sample runs for dashboard…")
    from packages.tracing.models import Run, RunStatus
    from packages.tracing.storage import get_storage

    storage = get_storage()

    sample_runs = [
        ("sql-001", "sql_agent", "sql_agent", 0.85, 0.0),
        ("sql-002", "sql_agent", "sql_agent", 0.72, 0.0),
        ("sql-003", "sql_agent", "sql_agent", 0.65, 1.0),
        ("sql-041", "sql_agent", "sql_agent", 1.0, 0.0),  # safety test passed
        ("rag-001", "rag_agent", "enterprise_rag", 0.91, 0.0),
        ("rag-002", "rag_agent", "enterprise_rag", 0.78, 0.0),
        ("rag-013", "rag_agent", "enterprise_rag", 1.0, 0.0),  # injection blocked
        ("sec-001", "security_agent", "github_security", 0.74, 0.0),
    ]

    for task_id, agent_type, benchmark, score, violations in sample_runs:
        run = Run(
            agent_type=agent_type,
            benchmark=benchmark,
            task_id=task_id,
            model_name="mock",
            model_provider="mock",
            status=RunStatus.RUNNING,
        )
        run.eval_scores = {"overall": score}
        if violations > 0:
            run.policy_violations = [{"policy_name": "sql_policy", "action": "blocked", "severity": "high", "reason": "Unsafe SQL detected"}]
        run.complete()
        storage.save_run(run)
        print(f"  ✓ {task_id} (score={score})")

    total = storage.count_runs()
    print(f"\n✓ Seeding complete — {total} runs in database")
    print(f"  Dashboard: http://localhost:3000")
    print(f"  API:       http://localhost:8000/docs")

if __name__ == "__main__":
    main()
