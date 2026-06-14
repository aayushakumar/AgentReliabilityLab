"""
LLM provider factory — supports Ollama, OpenAI, Anthropic, and mock mode.
"""
from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.0,
    **kwargs: Any,
):
    """
    Create and return a LangChain-compatible LLM.

    Provider auto-detected from environment if not specified.
    Falls back to mock mode if no provider is configured.
    """
    provider = provider or os.environ.get("LLM_PROVIDER", "mock")

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — falling back to mock")
            return _mock_llm()
        from langchain_openai import ChatOpenAI
        model_name = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=api_key,
            **kwargs,
        )

    if provider == "ollama":
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        model_name = model or os.environ.get("OLLAMA_MODEL", "llama3.2")
        try:
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=model_name,
                base_url=base_url,
                temperature=temperature,
                **kwargs,
            )
        except ImportError:
            logger.warning("langchain-ollama not available — falling back to mock")
            return _mock_llm()

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — falling back to mock")
            return _mock_llm()
        try:
            from langchain_anthropic import ChatAnthropic
            model_name = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
            return ChatAnthropic(
                model=model_name,
                temperature=temperature,
                api_key=api_key,
                **kwargs,
            )
        except ImportError:
            logger.warning("langchain-anthropic not available — falling back to mock")
            return _mock_llm()

    # Default: mock
    return _mock_llm()


def _mock_llm():
    """
    A deterministic mock LLM for testing without API keys.

    Returns predefined responses based on the last user message.
    """
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage, AIMessage
    from langchain_core.outputs import ChatResult, ChatGeneration
    from typing import List, Optional

    class MockChatLLM(BaseChatModel):
        """Deterministic mock LLM that generates SQL or answers based on keywords."""

        @property
        def _llm_type(self) -> str:
            return "mock"

        def _generate(
            self,
            messages: List[BaseMessage],
            stop: Optional[List[str]] = None,
            run_manager=None,
            **kwargs,
        ) -> ChatResult:
            last_msg = messages[-1].content if messages else ""
            response = self._generate_response(str(last_msg))
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=response))]
            )

        def _generate_response(self, prompt: str) -> str:
            prompt_lower = prompt.lower()

            # SQL agent patterns
            if any(kw in prompt_lower for kw in ["how many", "count", "total"]):
                if "order" in prompt_lower:
                    return "SELECT COUNT(*) as count FROM orders"
                if "product" in prompt_lower:
                    return "SELECT COUNT(*) as count FROM products"
                if "customer" in prompt_lower:
                    return "SELECT COUNT(*) as count FROM customers"
                return "SELECT COUNT(*) as count FROM orders"

            if "revenue" in prompt_lower or "sales" in prompt_lower:
                return "SELECT SUM(total_amount) as revenue FROM orders WHERE status = 'completed'"

            if "top" in prompt_lower and "product" in prompt_lower:
                return "SELECT p.name, SUM(oi.quantity) as units_sold FROM order_items oi JOIN products p ON oi.product_id = p.id GROUP BY p.id ORDER BY units_sold DESC LIMIT 5"

            if "customer" in prompt_lower and "average" in prompt_lower:
                return "SELECT AVG(total_amount) as avg_order_value FROM orders"

            if any(kw in prompt_lower for kw in ["list", "show", "find", "get"]):
                if "product" in prompt_lower:
                    return "SELECT id, name, price, category FROM products LIMIT 10"
                if "customer" in prompt_lower:
                    return "SELECT id, name, email, created_at FROM customers LIMIT 10"
                return "SELECT * FROM orders LIMIT 10"

            # RAG agent fallback
            if "?" in prompt:
                return "Based on the retrieved documents, the answer is: This information is contained in the provided context."

            # Security agent fallback
            if "vulnerabilit" in prompt_lower or "security" in prompt_lower:
                return '{"vulnerabilities": [{"file": "app.py", "line": 42, "vuln_type": "sql_injection", "severity": "high", "description": "Unsanitized user input in SQL query"}]}'

            return "I need more context to provide a complete answer."

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            return self._generate(messages, stop=stop, **kwargs)

    return MockChatLLM()
