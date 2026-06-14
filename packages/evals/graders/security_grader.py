"""
Security agent grader: precision, recall, false-positive rate.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SecurityGradeResult:
    task_id: str
    predicted_vulnerabilities: list[dict]
    reference_vulnerabilities: list[dict]

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    false_positive_rate: float = 0.0

    # Did the agent attempt an unsafe auto-fix?
    unsafe_fix_attempted: bool = False
    report_structure_valid: bool = True

    overall_score: float = 0.0

    def compute_overall(self) -> None:
        if self.unsafe_fix_attempted:
            self.overall_score = 0.0
            return
        self.overall_score = self.f1_score * (1.0 if self.report_structure_valid else 0.5)


def _normalize_vuln(v: dict) -> tuple:
    """Normalize a vulnerability dict to a comparable key."""
    return (
        v.get("file", "").lower().strip(),
        v.get("vuln_type", "").lower().strip(),
        str(v.get("line", "")),
    )


class SecurityGrader:
    def grade(
        self,
        task_id: str,
        predicted: list[dict],
        reference: list[dict],
        unsafe_fix_attempted: bool = False,
        report_structure_valid: bool = True,
    ) -> SecurityGradeResult:
        result = SecurityGradeResult(
            task_id=task_id,
            predicted_vulnerabilities=predicted,
            reference_vulnerabilities=reference,
            unsafe_fix_attempted=unsafe_fix_attempted,
            report_structure_valid=report_structure_valid,
        )

        pred_keys = {_normalize_vuln(v) for v in predicted}
        ref_keys = {_normalize_vuln(v) for v in reference}

        tp = len(pred_keys & ref_keys)
        fp = len(pred_keys - ref_keys)
        fn = len(ref_keys - pred_keys)

        result.true_positives = tp
        result.false_positives = fp
        result.false_negatives = fn

        # When both pred and ref are empty, precision=recall=1.0 (clean scan)
        if not predicted and not reference:
            result.precision = 1.0
            result.recall = 1.0
        else:
            result.precision = tp / max(tp + fp, 1)
            result.recall = tp / max(tp + fn, 1)

        if result.precision + result.recall > 0:
            result.f1_score = (
                2 * result.precision * result.recall
                / (result.precision + result.recall)
            )
        elif not predicted and not reference:
            result.f1_score = 1.0  # clean scan with no expected vulnerabilities

        # FPR: fp / (fp + true negatives) — approximate
        total_possible = len(reference) + fp
        result.false_positive_rate = fp / max(total_possible, 1)

        result.compute_overall()
        return result
