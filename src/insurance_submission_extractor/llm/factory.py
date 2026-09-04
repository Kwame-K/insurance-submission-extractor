from __future__ import annotations

from insurance_submission_extractor.config import LLMProvider, Settings
from insurance_submission_extractor.llm.base import LLMClient, LLMClientError
from insurance_submission_extractor.llm.gemini_client import GeminiClient


def create_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == LLMProvider.GEMINI:
        return GeminiClient(settings)

    if settings.llm_provider == LLMProvider.GROQ:
        raise LLMClientError(
            "The Groq client is not implemented yet. "
            "Set LLM_PROVIDER=gemini to run the current MVP."
        )

    raise LLMClientError(f"Unsupported LLM provider: '{settings.llm_provider}'.")
