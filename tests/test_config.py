from insurance_submission_extractor.config import (
    LLMProvider,
    Settings,
)


def test_settings_uses_default_models_without_env_file() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_provider == LLMProvider.GEMINI
    assert settings.gemini_model == "gemini-3.7-flash"
    assert settings.groq_model == "openai/gpt-oss-120b"


def test_settings_accepts_groq_provider() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="groq",
    )

    assert settings.llm_provider == LLMProvider.GROQ
