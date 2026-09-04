from __future__ import annotations

from insurance_submission_extractor.config import LLMProvider, Settings
from insurance_submission_extractor.llm.base import LLMClient, LLMClientError
from insurance_submission_extractor.llm.gemini_client import GeminiClient
from insurance_submission_extractor.llm.groq_client import GroqClient


def create_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == LLMProvider.GEMINI:
        return GeminiClient(settings)

    if settings.llm_provider == LLMProvider.GROQ:
        return GroqClient(settings)

    raise LLMClientError(f"Unsupported LLM provider: '{settings.llm_provider}'.")
