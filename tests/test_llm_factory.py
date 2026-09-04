from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm import (
    GeminiClient,
    GroqClient,
    create_llm_client,
)


def test_factory_creates_gemini_client() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="gemini",
        gemini_api_key="test-gemini-key",
    )

    client = create_llm_client(settings)

    assert isinstance(client, GeminiClient)
    assert client.provider == "gemini"


def test_factory_creates_groq_client() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="groq",
        groq_api_key="test-groq-key",
    )

    client = create_llm_client(settings)

    assert isinstance(client, GroqClient)
    assert client.provider == "groq"
