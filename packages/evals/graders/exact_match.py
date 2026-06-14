"""
Exact-match and fuzzy graders for deterministic evaluation.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_text(text: str) -> str:
    """Lowercase, strip whitespace, remove punctuation, normalize unicode."""
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def exact_match(prediction: str, reference: str, normalize: bool = True) -> float:
    """
    Returns 1.0 if prediction exactly matches reference, else 0.0.

    Args:
        normalize: Apply text normalization before comparison.
    """
    if normalize:
        return 1.0 if normalize_text(prediction) == normalize_text(reference) else 0.0
    return 1.0 if prediction.strip() == reference.strip() else 0.0


def contains_match(prediction: str, reference: str, normalize: bool = True) -> float:
    """Returns 1.0 if prediction contains the reference string."""
    pred = normalize_text(prediction) if normalize else prediction.strip()
    ref = normalize_text(reference) if normalize else reference.strip()
    return 1.0 if ref in pred else 0.0


def set_match(prediction: list[Any], reference: list[Any]) -> float:
    """
    Returns F1 score between predicted and reference sets.
    Useful for multi-label grading.
    """
    pred_set = set(str(p).lower().strip() for p in prediction)
    ref_set = set(str(r).lower().strip() for r in reference)

    if not pred_set and not ref_set:
        return 1.0
    if not pred_set or not ref_set:
        return 0.0

    tp = len(pred_set & ref_set)
    precision = tp / len(pred_set)
    recall = tp / len(ref_set)

    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def numeric_match(
    prediction: float | int | str,
    reference: float | int | str,
    tolerance: float = 0.01,
) -> float:
    """Returns 1.0 if |prediction - reference| / reference ≤ tolerance."""
    try:
        p = float(prediction)
        r = float(reference)
    except (ValueError, TypeError):
        return 0.0

    if r == 0:
        return 1.0 if p == 0 else 0.0
    return 1.0 if abs(p - r) / abs(r) <= tolerance else 0.0


def row_set_match(
    predicted_rows: list[dict],
    reference_rows: list[dict],
    key_columns: list[str] | None = None,
) -> float:
    """
    Compare two lists of row dicts.

    If key_columns is provided, only compare those columns.
    Returns F1 score over rows (treating each row as a set element).
    """
    def row_to_key(row: dict) -> frozenset:
        if key_columns:
            return frozenset(
                (k, str(v).lower().strip())
                for k, v in row.items()
                if k in key_columns
            )
        return frozenset((k, str(v).lower().strip()) for k, v in row.items())

    pred_keys = {row_to_key(r) for r in predicted_rows}
    ref_keys = {row_to_key(r) for r in reference_rows}

    if not pred_keys and not ref_keys:
        return 1.0
    if not pred_keys or not ref_keys:
        return 0.0

    tp = len(pred_keys & ref_keys)
    precision = tp / len(pred_keys)
    recall = tp / len(ref_keys)

    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
