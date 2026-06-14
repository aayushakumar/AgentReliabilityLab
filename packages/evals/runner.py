"""
Evaluation runner — executes a batch of benchmark tasks and collects results.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.tracing.models import Run, RunStatus
from packages.tracing.storage import get_storage

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkTask:
    """A single benchmark task definition."""
    task_id: str
    benchmark: str
    question: str
    expected_output: Any = None
    expected_sql: str | None = None
    expected_rows: list[dict] | None = None
    expected_doc_ids: list[str] | None = None
    reference_answer: str | None = None
    reference_citations: list[str] | None = None
    reference_vulnerabilities: list[dict] | None = None
    tags: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    """Result of running a single benchmark task through the eval pipeline."""
    task_id: str
    run_id: str
    benchmark: str
    scores: dict[str, float]
    overall_score: float
    latency_ms: float
    total_tokens: int
    cost_usd: float
    policy_violations: int
    status: str  # "passed" | "failed" | "error"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    """Aggregated report across all tasks in a benchmark run."""
    benchmark: str
    model_name: str
    framework: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    error_tasks: int

    # Aggregate metrics
    avg_overall_score: float = 0.0
    avg_latency_ms: float = 0.0
    avg_tokens: float = 0.0
    avg_cost_usd: float = 0.0
    total_policy_violations: int = 0
    task_success_rate: float = 0.0  # fraction with overall_score >= 0.7

    per_metric_averages: dict[str, float] = field(default_factory=dict)
    results: list[EvalResult] = field(default_factory=list)

    def compute_aggregates(self, pass_threshold: float = 0.7) -> None:
        if not self.results:
            return
        completed = [r for r in self.results if r.status != "error"]
        if not completed:
            return

        self.avg_overall_score = sum(r.overall_score for r in completed) / len(completed)
        self.avg_latency_ms = sum(r.latency_ms for r in completed) / len(completed)
        self.avg_tokens = sum(r.total_tokens for r in completed) / len(completed)
        self.avg_cost_usd = sum(r.cost_usd for r in completed) / len(completed)
        self.total_policy_violations = sum(r.policy_violations for r in completed)
        self.task_success_rate = (
            sum(1 for r in completed if r.overall_score >= pass_threshold) / len(completed)
        )

        # Per-metric averages
        all_metrics: set[str] = set()
        for r in completed:
            all_metrics.update(r.scores.keys())
        for metric in all_metrics:
            vals = [r.scores[metric] for r in completed if metric in r.scores]
            if vals:
                self.per_metric_averages[metric] = sum(vals) / len(vals)


class EvalRunner:
    """
    Runs a batch of benchmark tasks and produces an EvalReport.

    Usage:
        runner = EvalRunner(agent_fn=my_agent, grader_fn=my_grader)
        report = runner.run(tasks, benchmark="sql_agent")
    """

    def __init__(
        self,
        *,
        model_name: str = "unknown",
        framework: str = "langgraph",
        save_runs: bool = True,
    ):
        self.model_name = model_name
        self.framework = framework
        self.save_runs = save_runs
        self._storage = get_storage() if save_runs else None

    def run(
        self,
        tasks: list[BenchmarkTask],
        agent_fn: Callable[[BenchmarkTask], tuple[Run, dict[str, Any]]],
        grader_fn: Callable[[BenchmarkTask, Run, dict[str, Any]], EvalResult],
        benchmark: str = "unknown",
        verbose: bool = True,
    ) -> BenchmarkReport:
        """
        Execute all tasks through agent_fn, then grade with grader_fn.

        Args:
            tasks: List of benchmark tasks to run.
            agent_fn: Callable(task) -> (Run, agent_output_dict)
            grader_fn: Callable(task, run, agent_output) -> EvalResult
            benchmark: Name for the report.
        """
        results: list[EvalResult] = []
        errors = 0

        logger.info("Starting benchmark '%s' with %d tasks", benchmark, len(tasks))

        for i, task in enumerate(tasks):
            if verbose:
                print(f"  [{i + 1}/{len(tasks)}] Task {task.task_id}...", end="", flush=True)

            t0 = time.monotonic()
            try:
                run, agent_output = agent_fn(task)
                eval_result = grader_fn(task, run, agent_output)

                if self.save_runs and self._storage:
                    self._storage.save_run(run)

                elapsed = (time.monotonic() - t0) * 1000
                if verbose:
                    print(f" score={eval_result.overall_score:.2f} ({elapsed:.0f}ms)")

                results.append(eval_result)

            except Exception as e:
                elapsed = (time.monotonic() - t0) * 1000
                if verbose:
                    print(f" ERROR: {e}")
                logger.exception("Task %s failed", task.task_id)
                errors += 1
                results.append(
                    EvalResult(
                        task_id=task.task_id,
                        run_id="",
                        benchmark=benchmark,
                        scores={},
                        overall_score=0.0,
                        latency_ms=elapsed,
                        total_tokens=0,
                        cost_usd=0.0,
                        policy_violations=0,
                        status="error",
                        error=str(e),
                    )
                )

        completed = len(results) - errors
        passed = sum(1 for r in results if r.status == "passed")

        report = BenchmarkReport(
            benchmark=benchmark,
            model_name=self.model_name,
            framework=self.framework,
            total_tasks=len(tasks),
            completed_tasks=completed,
            failed_tasks=sum(1 for r in results if r.status == "failed"),
            error_tasks=errors,
            results=results,
        )
        report.compute_aggregates()

        logger.info(
            "Benchmark '%s' complete: %d/%d tasks, avg_score=%.2f",
            benchmark, completed, len(tasks), report.avg_overall_score,
        )
        return report

    def save_report(self, report: BenchmarkReport, path: str) -> None:
        """Save report as JSON."""
        data = {
            "benchmark": report.benchmark,
            "model_name": report.model_name,
            "framework": report.framework,
            "total_tasks": report.total_tasks,
            "completed_tasks": report.completed_tasks,
            "failed_tasks": report.failed_tasks,
            "error_tasks": report.error_tasks,
            "avg_overall_score": report.avg_overall_score,
            "avg_latency_ms": report.avg_latency_ms,
            "avg_tokens": report.avg_tokens,
            "avg_cost_usd": report.avg_cost_usd,
            "total_policy_violations": report.total_policy_violations,
            "task_success_rate": report.task_success_rate,
            "per_metric_averages": report.per_metric_averages,
            "results": [
                {
                    "task_id": r.task_id,
                    "run_id": r.run_id,
                    "scores": r.scores,
                    "overall_score": r.overall_score,
                    "latency_ms": r.latency_ms,
                    "total_tokens": r.total_tokens,
                    "policy_violations": r.policy_violations,
                    "status": r.status,
                    "error": r.error,
                }
                for r in report.results
            ],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Report saved to %s", path)
