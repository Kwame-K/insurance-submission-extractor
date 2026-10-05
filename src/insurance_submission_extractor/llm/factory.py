from __future__ import annotations

from insurance_submission_extractor.config import LLMProvider, Settings
from insurance_submission_extractor.llm.base import LLMClient, LLMClientError
from insurance_submission_extractor.llm.fallback import FallbackLLMClient
from insurance_submission_extractor.llm.gemini_client import GeminiClient
from insurance_submission_extractor.llm.groq_client import GroqClient


def _create_single_client(settings: Settings, provider: LLMProvider) -> LLMClient:
    if provider == LLMProvider.GEMINI:
        return GeminiClient(settings)

    if provider == LLMProvider.GROQ:
        return GroqClient(settings)

    raise LLMClientError(f"Unsupported LLM provider: '{provider}'.")


def create_llm_client(settings: Settings) -> LLMClient:
    primary = _create_single_client(settings, settings.llm_provider)
    fallback_provider = settings.llm_fallback_provider

    if fallback_provider is None or fallback_provider == settings.llm_provider:
        return primary

    fallback = _create_single_client(settings, fallback_provider)

    return FallbackLLMClient(primary=primary, fallback=fallback)
