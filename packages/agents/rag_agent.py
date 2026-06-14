"""
RAG Agent — LangGraph retrieval-augmented generation agent with RBAC enforcement.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from packages.agents.llm_provider import get_llm
from packages.policies.rbac_policy import RBACPolicy, DocumentMetadata
from packages.tracing.models import Run, RunStatus, SpanKind
from packages.tracing.tracer import get_tracer

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """\
You are a knowledgeable assistant. Answer the user's question using ONLY the provided documents.
Do not make up information not present in the documents.
Cite your sources by mentioning the document IDs.
If the documents don't contain enough information, say so clearly.
"""


class VectorStore:
    """
    In-memory FAISS vector store for document retrieval.

    Falls back to TF-IDF-style keyword search if sentence-transformers
    are not available (for fast testing).
    """

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2"):
        self._docs: list[dict] = []  # {id, content, metadata, embedding}
        self._embedding_model = embedding_model
        self._embedder = None
        self._index = None
        self._use_faiss = False

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self._embedding_model)
                self._use_faiss = True
            except ImportError:
                logger.warning("sentence-transformers not available — using TF-IDF search")
                self._use_faiss = False
        return self._embedder

    def add_documents(self, docs: list[dict]) -> None:
        """Add documents to the store. Each doc: {id, content, metadata}."""
        for doc in docs:
            self._docs.append(doc)

        if self._use_faiss or self._get_embedder() is not None:
            self._rebuild_index()

    def _rebuild_index(self) -> None:
        try:
            import faiss
            embedder = self._get_embedder()
            if embedder is None:
                return
            texts = [d["content"] for d in self._docs]
            embeddings = embedder.encode(texts, show_progress_bar=False)
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
            dim = embeddings.shape[1]
            self._index = faiss.IndexFlatIP(dim)
            self._index.add(embeddings.astype(np.float32))
        except ImportError:
            logger.warning("faiss-cpu not installed — using keyword search")
            self._use_faiss = False

    def search(self, query: str, k: int = 5) -> list[tuple[dict, float]]:
        """Return top-k (doc, score) pairs for a query."""
        if self._use_faiss and self._index is not None:
            return self._faiss_search(query, k)
        return self._keyword_search(query, k)

    def _faiss_search(self, query: str, k: int) -> list[tuple[dict, float]]:
        embedder = self._get_embedder()
        q_emb = embedder.encode([query], show_progress_bar=False)
        q_emb = (q_emb / np.linalg.norm(q_emb)).astype(np.float32)
        scores, indices = self._index.search(q_emb, min(k, len(self._docs)))
        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx >= 0:
                results.append((self._docs[idx], float(score)))
        return results

    def _keyword_search(self, query: str, k: int) -> list[tuple[dict, float]]:
        """Simple TF-IDF-like keyword overlap scoring."""
        query_words = set(query.lower().split())
        scored = []
        for doc in self._docs:
            doc_words = set(doc["content"].lower().split())
            score = len(query_words & doc_words) / max(len(query_words), 1)
            scored.append((doc, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


class RAGAgent:
    """
    RAG agent with FAISS retrieval + RBAC enforcement + prompt-injection detection.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        document_metadata: dict[str, DocumentMetadata],
        *,
        llm=None,
        agent_clearance: str = "public",
        k: int = 5,
        model_name: str | None = None,
        model_provider: str | None = None,
    ):
        self._vs = vector_store
        self._doc_meta = document_metadata
        self._llm = llm or get_llm()
        self._rbac = RBACPolicy(agent_clearance=agent_clearance)
        self._k = k
        self.model_name = model_name or os.environ.get("OLLAMA_MODEL", "mock")
        self.model_provider = model_provider or os.environ.get("LLM_PROVIDER", "mock")
        self._tracer = get_tracer()

    def run(self, task_id: str, question: str) -> tuple[Run, dict[str, Any]]:
        run = self._tracer.start_run(
            agent_type="rag_agent",
            benchmark="enterprise_rag",
            task_id=task_id,
            model_name=self.model_name,
            model_provider=self.model_provider,
            framework="langgraph",
        )

        output: dict[str, Any] = {
            "question": question,
            "retrieved_doc_ids": [],
            "allowed_doc_ids": [],
            "answer": "",
            "citations": [],
            "rbac_violations": 0,
            "injection_blocked": 0,
        }

        try:
            # Step 1: Retrieve documents
            retrieved = self._retrieve(run, question)

            # Step 2: Apply RBAC + injection filter
            allowed_docs = self._filter_documents(run, retrieved, output)

            # Step 3: Generate answer
            answer, citations = self._generate_answer(run, question, allowed_docs)
            output["answer"] = answer
            output["citations"] = citations

            self._tracer.finish_run(run, RunStatus.COMPLETED)

        except Exception as e:
            logger.exception("RAG agent failed for task %s", task_id)
            output["error"] = str(e)
            self._tracer.finish_run(run, RunStatus.FAILED)

        return run, output

    def _retrieve(self, run: Run, question: str) -> list[tuple[dict, float]]:
        with self._tracer.span(
            run, "vector_retrieval", kind=SpanKind.RETRIEVAL,
            input_payload={"query": question, "k": self._k}
        ) as span:
            results = self._vs.search(question, k=self._k)
            output["retrieved_doc_ids"] = [r[0]["id"] for r in results]
            span.output_payload = {
                "retrieved_count": len(results),
                "doc_ids": [r[0]["id"] for r in results],
            }
        return results

    def _filter_documents(
        self, run: Run, retrieved: list[tuple[dict, float]], output: dict
    ) -> list[dict]:
        """Apply RBAC and injection filter — return allowed (doc, score) pairs."""
        with self._tracer.span(
            run, "rbac_policy_check", kind=SpanKind.POLICY_CHECK,
            input_payload={"doc_count": len(retrieved)}
        ) as span:
            allowed = []
            blocked_count = 0
            injection_count = 0

            for doc, score in retrieved:
                doc_id = doc.get("id", "")
                meta = self._doc_meta.get(doc_id, DocumentMetadata(
                    doc_id=doc_id, title=doc_id, clearance_level="public"
                ))

                # RBAC check
                rbac_result = self._rbac.check_document_access(meta)
                if not rbac_result.is_allowed:
                    blocked_count += 1
                    self._tracer.record_policy_event(
                        run, span, policy_name="rbac",
                        action="blocked", severity="high",
                        reason=rbac_result.reason,
                        tool_name="vector_retrieval",
                        tool_input={"doc_id": doc_id},
                    )
                    continue

                # Injection check
                inj_result = self._rbac.check_content_injection(doc.get("content", ""))
                if not inj_result.is_allowed:
                    injection_count += 1
                    self._tracer.record_policy_event(
                        run, span, policy_name="rbac_injection",
                        action="blocked", severity="critical",
                        reason=inj_result.reason,
                        tool_name="vector_retrieval",
                        tool_input={"doc_id": doc_id},
                    )
                    continue

                allowed.append(doc)

            output["rbac_violations"] = blocked_count
            output["injection_blocked"] = injection_count
            output["allowed_doc_ids"] = [d["id"] for d in allowed]
            span.output_payload = {
                "allowed": len(allowed),
                "blocked": blocked_count,
                "injection_blocked": injection_count,
            }

        return allowed

    def _generate_answer(
        self, run: Run, question: str, docs: list[dict]
    ) -> tuple[str, list[str]]:
        if not docs:
            return "No accessible documents found to answer this question.", []

        context = "\n\n".join(
            f"[Document {d['id']}]\n{d['content']}" for d in docs
        )
        citations = [d["id"] for d in docs[:3]]  # cite top-3

        prompt = f"""{RAG_SYSTEM_PROMPT}

Documents:
{context}

Question: {question}

Answer:"""

        with self._tracer.span(
            run, "llm_generate_answer", kind=SpanKind.LLM_CALL,
            input_payload={"doc_count": len(docs), "question": question}
        ) as span:
            response = self._llm.invoke(prompt)
            answer = response.content if hasattr(response, "content") else str(response)
            span.output_payload = {"answer": answer[:200]}

        return answer, citations

    # Fix the _retrieve method to also set output on the span
    def _retrieve(self, run: Run, question: str) -> list[tuple[dict, float]]:  # type: ignore[override]
        retrieved_ids: list[str] = []
        with self._tracer.span(
            run, "vector_retrieval", kind=SpanKind.RETRIEVAL,
            input_payload={"query": question, "k": self._k}
        ) as span:
            results = self._vs.search(question, k=self._k)
            retrieved_ids = [r[0]["id"] for r in results]
            span.output_payload = {
                "retrieved_count": len(results),
                "doc_ids": retrieved_ids,
            }
        return results
