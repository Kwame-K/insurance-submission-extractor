from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from insurance_submission_extractor.pricing import ModelPrice, PriceBook


class LLMProvider(StrEnum):
    GEMINI = "gemini"
    GROQ = "groq"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: LLMProvider = LLMProvider.GEMINI
    llm_fallback_provider: LLMProvider | None = None
    extraction_log_path: Path | None = None
    database_url: str | None = None
    database_auto_migrate: bool = True

    gemini_input_price_per_million_usd: float | None = Field(default=None, ge=0)
    gemini_output_price_per_million_usd: float | None = Field(default=None, ge=0)
    groq_input_price_per_million_usd: float | None = Field(default=None, ge=0)
    groq_output_price_per_million_usd: float | None = Field(default=None, ge=0)

    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="GEMINI_API_KEY",
    )
    gemini_model: str = Field(
        default="gemini-3.7-flash",
        validation_alias="GEMINI_MODEL",
    )

    groq_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="GROQ_API_KEY",
    )
    groq_model: str = Field(
        default="openai/gpt-oss-120b",
        validation_alias="GROQ_MODEL",
    )

    @field_validator(
        "llm_fallback_provider",
        "extraction_log_path",
        "database_url",
        "gemini_input_price_per_million_usd",
        "gemini_output_price_per_million_usd",
        "groq_input_price_per_million_usd",
        "groq_output_price_per_million_usd",
        mode="before",
    )
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        """Treat an empty optional setting (for example `NAME=`) as not configured."""
        return None if isinstance(value, str) and not value.strip() else value

    def price_book(self) -> PriceBook:
        """Return configured token prices. Providers without both prices stay unpriced."""
        prices: dict[str, ModelPrice] = {}

        for provider in LLMProvider:
            input_price = getattr(self, f"{provider.value}_input_price_per_million_usd")
            output_price = getattr(self, f"{provider.value}_output_price_per_million_usd")
            if input_price is not None and output_price is not None:
                prices[provider.value] = ModelPrice(
                    input_per_million_usd=input_price,
                    output_per_million_usd=output_price,
                )

        return PriceBook(prices)
