"""GitHub Security Agent Benchmark Runner."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

BENCHMARK_DIR = Path(__file__).parent
FIXTURES_DIR = BENCHMARK_DIR / "repos"
REPORTS_DIR = ROOT / "data" / "reports"


def load_tasks(max_tasks=None, task_ids=None):
    from packages.evals.runner import BenchmarkTask
    with open(BENCHMARK_DIR / "tasks.json") as f:
        raw = json.load(f)
    tasks = []
    for t in raw:
        if task_ids and t["task_id"] not in task_ids:
            continue
        tasks.append(BenchmarkTask(
            task_id=t["task_id"],
            benchmark="github_security",
            question=t["description"],
            reference_vulnerabilities=t.get("reference_vulnerabilities", []),
            tags=t.get("tags", {}),
            metadata={
                "repo": t["repo"],
                "files_to_scan": t.get("files_to_scan"),
            },
        ))
    if max_tasks:
        tasks = tasks[:max_tasks]
    return tasks


def run_single_task(task_id, model_provider="mock", model_name=None):
    tasks = load_tasks(task_ids=[task_id])
    if not tasks:
        print(f"Task '{task_id}' not found")
        return
    _run_tasks(tasks, model_provider=model_provider, model_name=model_name or model_provider)


def run(max_tasks=5, model_provider="mock", model_name=None, task_ids=None, verbose=True):
    tasks = load_tasks(max_tasks=max_tasks, task_ids=task_ids)
    _run_tasks(tasks, model_provider=model_provider, model_name=model_name or model_provider, verbose=verbose)


def _run_tasks(tasks, model_provider="mock", model_name="mock", verbose=True):
    from packages.agents.llm_provider import get_llm
    from packages.agents.security_agent import SecurityAgent
    from packages.evals.graders.security_grader import SecurityGrader
    from packages.evals.runner import EvalRunner, EvalResult
    from packages.tracing.models import Run
    from packages.tracing.storage import get_storage

    llm = get_llm(provider=model_provider)
    grader = SecurityGrader()
    agent = SecurityAgent(
        fixtures_dir=str(FIXTURES_DIR),
        llm=llm,
        model_name=model_name,
        model_provider=model_provider,
    )
    runner = EvalRunner(model_name=model_name, framework="langgraph", save_runs=True)

    def agent_fn(task):
        return agent.run(
            task_id=task.task_id,
            repo=task.metadata["repo"],
            files_to_scan=task.metadata.get("files_to_scan"),
        )

    def grader_fn(task, run: Run, output: dict) -> EvalResult:
        grade = grader.grade(
            task_id=task.task_id,
            predicted=output.get("vulnerabilities", []),
            reference=task.reference_vulnerabilities or [],
            unsafe_fix_attempted=output.get("unsafe_fix_attempted", False),
        )
        scores = {
            "precision": grade.precision,
            "recall": grade.recall,
            "f1_score": grade.f1_score,
            "false_positive_rate": grade.false_positive_rate,
            "overall": grade.overall_score,
        }
        run.eval_scores = scores
        get_storage().save_run(run)
        overall = grade.overall_score
        return EvalResult(
            task_id=task.task_id, run_id=run.run_id, benchmark="github_security",
            scores=scores, overall_score=overall,
            latency_ms=run.total_latency_ms, total_tokens=run.total_tokens,
            cost_usd=run.total_cost_usd, policy_violations=len(run.policy_violations),
            status="passed" if overall >= 0.4 else "failed",
        )

    print(f"\nGitHub Security Benchmark — {len(tasks)} tasks (provider: {model_provider})")
    print("=" * 60)
    report = runner.run(tasks=tasks, agent_fn=agent_fn, grader_fn=grader_fn,
                        benchmark="github_security", verbose=verbose)

    print(f"\nSuccess rate: {report.task_success_rate:.1%}  Avg score: {report.avg_overall_score:.3f}")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    runner.save_report(report, str(REPORTS_DIR / "security_benchmark.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-tasks", type=int, default=5)
    parser.add_argument("--provider", default="mock")
    args = parser.parse_args()
    run(max_tasks=args.max_tasks, model_provider=args.provider)
