from pathlib import Path

import pytest

from insurance_submission_extractor.config import Settings


def test_empty_optional_settings_mean_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "LLM_FALLBACK_PROVIDER",
        "EXTRACTION_LOG_PATH",
        "GEMINI_INPUT_PRICE_PER_MILLION_USD",
        "GROQ_OUTPUT_PRICE_PER_MILLION_USD",
    ):
        monkeypatch.setenv(name, "")

    settings = Settings(_env_file=None)

    assert settings.llm_fallback_provider is None
    assert settings.extraction_log_path is None
    assert settings.price_book().prices == {}


def test_non_empty_values_are_still_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTRACTION_LOG_PATH", "logs/x.jsonl")

    assert Settings(_env_file=None).extraction_log_path == Path("logs/x.jsonl")
