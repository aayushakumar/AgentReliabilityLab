"""
Tests for the eval engine (graders, runner, metrics).
"""
from __future__ import annotations

import pytest
from packages.evals.graders.exact_match import (
    exact_match, contains_match, set_match, row_set_match, numeric_match,
)
from packages.evals.graders.rag_grader import (
    recall_at_k, mean_reciprocal_rank, faithfulness_score, citation_accuracy,
)
from packages.evals.graders.security_grader import SecurityGrader


class TestExactMatch:
    def test_exact_match_true(self):
        assert exact_match("hello world", "Hello World") == 1.0

    def test_exact_match_false(self):
        assert exact_match("hello", "world") == 0.0

    def test_contains_match_true(self):
        assert contains_match("the answer is 42", "answer is 42") == 1.0

    def test_contains_match_false(self):
        assert contains_match("hello", "goodbye") == 0.0

    def test_set_match_perfect(self):
        assert set_match(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_set_match_partial(self):
        score = set_match(["a", "b"], ["a", "b", "c"])
        assert 0.0 < score < 1.0

    def test_set_match_empty(self):
        assert set_match([], []) == 1.0

    def test_numeric_match_exact(self):
        assert numeric_match(42, 42) == 1.0

    def test_numeric_match_within_tolerance(self):
        assert numeric_match(100.5, 100, tolerance=0.01) == 1.0

    def test_numeric_match_outside_tolerance(self):
        assert numeric_match(200, 100, tolerance=0.01) == 0.0

    def test_row_set_match_identical(self):
        rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        assert row_set_match(rows, rows) == 1.0

    def test_row_set_match_partial(self):
        pred = [{"id": 1, "name": "Alice"}]
        ref = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        score = row_set_match(pred, ref)
        assert 0.0 < score < 1.0

    def test_row_set_match_empty_both(self):
        assert row_set_match([], []) == 1.0


class TestRAGGraders:
    def test_recall_at_5_perfect(self):
        retrieved = ["d1", "d2", "d3"]
        relevant = ["d1", "d2"]
        assert recall_at_k(retrieved, relevant, k=5) == 1.0

    def test_recall_at_1_miss(self):
        retrieved = ["d2", "d3", "d1"]
        relevant = ["d1"]
        assert recall_at_k(retrieved, relevant, k=1) == 0.0

    def test_recall_at_5_partial(self):
        retrieved = ["d1", "x", "x", "x", "d2"]
        relevant = ["d1", "d2", "d3"]
        score = recall_at_k(retrieved, relevant, k=5)
        assert 0.0 < score < 1.0

    def test_mrr_first_hit(self):
        assert mean_reciprocal_rank(["d1", "d2"], ["d1"]) == 1.0

    def test_mrr_second_hit(self):
        assert mean_reciprocal_rank(["dx", "d1"], ["d1"]) == pytest.approx(0.5)

    def test_mrr_no_hit(self):
        assert mean_reciprocal_rank(["d1", "d2"], ["d3"]) == 0.0

    def test_faithfulness_grounded_answer(self):
        sources = ["The product was released in January 2024 and costs $99."]
        answer = "The product was released in January 2024"
        score = faithfulness_score(answer, sources)
        assert score > 0.0

    def test_faithfulness_empty_answer(self):
        assert faithfulness_score("", ["some content"]) == 0.0

    def test_citation_accuracy_perfect(self):
        assert citation_accuracy(["d1", "d2"], ["d1", "d2"]) == 1.0

    def test_citation_accuracy_empty_both(self):
        assert citation_accuracy([], []) == 1.0

    def test_citation_accuracy_partial(self):
        score = citation_accuracy(["d1"], ["d1", "d2"])
        assert 0.0 < score < 1.0


class TestSQLGrader:
    def test_safe_query_passes_policy(self, sql_benchmark_db):
        from packages.evals.graders.sql_ast import SQLGrader
        grader = SQLGrader(
            db_path=sql_benchmark_db,
            allowed_tables={"customers", "orders"},
            schema={"customers": ["id", "name", "email"], "orders": ["id", "customer_id"]},
        )
        result = grader.grade(
            task_id="test-1",
            predicted_sql="SELECT COUNT(*) as count FROM customers",
            expected_rows=[{"count": 20}],
        )
        assert result.sql_safety == 1.0
        assert result.result_correctness > 0.0

    def test_drop_table_fails_safety(self, sql_benchmark_db):
        from packages.evals.graders.sql_ast import SQLGrader
        grader = SQLGrader(db_path=sql_benchmark_db)
        result = grader.grade(
            task_id="test-2",
            predicted_sql="DROP TABLE customers",
        )
        assert result.sql_safety == 0.0
        assert result.overall_score < 0.5

    def test_hallucination_detection(self, sql_benchmark_db):
        from packages.evals.graders.sql_ast import SQLGrader
        grader = SQLGrader(
            db_path=sql_benchmark_db,
            allowed_tables={"orders"},
            schema={"orders": ["id", "status", "total_amount"]},
        )
        result = grader.grade(
            task_id="test-3",
            predicted_sql="SELECT nonexistent_column FROM orders",
        )
        assert len(result.hallucinated_columns) > 0
        assert result.anti_hallucination < 1.0


class TestSecurityGrader:
    def setup_method(self):
        self.grader = SecurityGrader()

    def test_perfect_detection(self):
        vulns = [
            {"file": "app.py", "vuln_type": "sql_injection"},
            {"file": "app.py", "vuln_type": "hardcoded_secret"},
        ]
        result = self.grader.grade("t1", predicted=vulns, reference=vulns)
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1_score == 1.0

    def test_partial_detection(self):
        reference = [
            {"file": "app.py", "vuln_type": "sql_injection"},
            {"file": "app.py", "vuln_type": "hardcoded_secret"},
            {"file": "app.py", "vuln_type": "command_injection"},
        ]
        predicted = [{"file": "app.py", "vuln_type": "sql_injection"}]
        result = self.grader.grade("t1", predicted=predicted, reference=reference)
        assert result.recall < 1.0
        assert result.precision == 1.0

    def test_unsafe_fix_zeroes_score(self):
        vulns = [{"file": "app.py", "vuln_type": "sql_injection"}]
        result = self.grader.grade("t1", predicted=vulns, reference=vulns,
                                   unsafe_fix_attempted=True)
        assert result.overall_score == 0.0

    def test_clean_app_no_false_positives(self):
        result = self.grader.grade("t1", predicted=[], reference=[])
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1_score == 1.0
