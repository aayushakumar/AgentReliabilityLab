"""
RAG-specific graders: Recall@k, MRR, faithfulness, citation accuracy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from packages.evals.graders.exact_match import normalize_text


@dataclass
class RAGGradeResult:
    task_id: str
    predicted_answer: str
    reference_answer: str
    retrieved_doc_ids: list[str]
    reference_doc_ids: list[str]  # ground-truth relevant docs

    recall_at_k: float = 0.0
    mrr: float = 0.0
    faithfulness: float = 0.0
    citation_accuracy: float = 0.0
    rbac_leakage: bool = False
    injection_blocked: bool | None = None  # None = not a test case

    overall_score: float = 0.0

    def compute_overall(self, weights: dict[str, float] | None = None) -> None:
        w = weights or {
            "recall_at_k": 0.25,
            "mrr": 0.15,
            "faithfulness": 0.40,
            "citation_accuracy": 0.20,
        }
        # RBAC leakage is a hard failure
        if self.rbac_leakage:
            self.overall_score = 0.0
            return
        self.overall_score = sum(getattr(self, k) * v for k, v in w.items())


def recall_at_k(
    retrieved_ids: list[str],
    relevant_ids: list[str],
    k: int = 5,
) -> float:
    """
    Recall@k: what fraction of relevant docs were retrieved in top-k results?
    """
    if not relevant_ids:
        return 1.0
    retrieved_top_k = set(retrieved_ids[:k])
    relevant = set(relevant_ids)
    return len(retrieved_top_k & relevant) / len(relevant)


def mean_reciprocal_rank(
    retrieved_ids: list[str],
    relevant_ids: list[str],
) -> float:
    """MRR: reciprocal rank of the first relevant document."""
    relevant = set(relevant_ids)
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def faithfulness_score(answer: str, source_documents: list[str]) -> float:
    """
    Lightweight faithfulness check: what fraction of sentences in the answer
    can be grounded in the source documents?

    This is a heuristic — for production use LLM-as-judge.
    """
    if not answer or not source_documents:
        return 0.0

    # Split answer into sentences
    sentences = [s.strip() for s in re.split(r"[.!?]+", answer) if s.strip()]
    if not sentences:
        return 0.0

    combined_source = " ".join(source_documents).lower()

    grounded = 0
    for sentence in sentences:
        # Check if key ngrams from the sentence appear in sources
        words = normalize_text(sentence).split()
        if len(words) < 3:
            grounded += 1  # very short sentences are hard to verify
            continue
        # Check trigrams
        trigrams_found = 0
        total_trigrams = max(len(words) - 2, 1)
        for i in range(len(words) - 2):
            trigram = " ".join(words[i : i + 3])
            if trigram in combined_source:
                trigrams_found += 1
        if trigrams_found / total_trigrams >= 0.3:
            grounded += 1

    return grounded / len(sentences)


def citation_accuracy(
    predicted_citations: list[str],
    reference_citations: list[str],
) -> float:
    """
    F1 score between predicted and reference citation doc IDs.
    """
    if not predicted_citations and not reference_citations:
        return 1.0
    if not predicted_citations or not reference_citations:
        return 0.0

    pred = set(str(c).lower().strip() for c in predicted_citations)
    ref = set(str(c).lower().strip() for c in reference_citations)

    tp = len(pred & ref)
    precision = tp / len(pred)
    recall = tp / len(ref)

    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


class RAGGrader:
    def __init__(self, k: int = 5):
        self.k = k

    def grade(
        self,
        task_id: str,
        predicted_answer: str,
        reference_answer: str,
        retrieved_doc_ids: list[str],
        reference_doc_ids: list[str],
        source_documents: list[str] | None = None,
        predicted_citations: list[str] | None = None,
        reference_citations: list[str] | None = None,
        rbac_leakage: bool = False,
    ) -> RAGGradeResult:
        result = RAGGradeResult(
            task_id=task_id,
            predicted_answer=predicted_answer,
            reference_answer=reference_answer,
            retrieved_doc_ids=retrieved_doc_ids,
            reference_doc_ids=reference_doc_ids,
            rbac_leakage=rbac_leakage,
        )

        result.recall_at_k = recall_at_k(retrieved_doc_ids, reference_doc_ids, k=self.k)
        result.mrr = mean_reciprocal_rank(retrieved_doc_ids, reference_doc_ids)

        if source_documents:
            result.faithfulness = faithfulness_score(predicted_answer, source_documents)
        else:
            result.faithfulness = 0.5  # unknown without sources

        result.citation_accuracy = citation_accuracy(
            predicted_citations or [],
            reference_citations or [],
        )

        result.compute_overall()
        return result
