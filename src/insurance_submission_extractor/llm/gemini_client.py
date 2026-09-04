from __future__ import annotations

from google import genai
from pydantic import ValidationError

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm.base import LLMClientError
from insurance_submission_extractor.prompts import (
    SYSTEM_INSTRUCTIONS,
    build_extraction_prompt,
)
from insurance_submission_extractor.schemas import InsuranceSubmission


class GeminiClient:
    provider = "gemini"

    def __init__(self, settings: Settings) -> None:
        if settings.gemini_api_key is None:
            raise LLMClientError("GEMINI_API_KEY is required when using the Gemini provider.")

        self.model = settings.gemini_model
        self._client = genai.Client(
            api_key=settings.gemini_api_key.get_secret_value(),
        )

    def extract_submission(
        self,
        submission_text: str,
        submission_id: str,
    ) -> InsuranceSubmission:
        prompt = build_extraction_prompt(
            submission_text=submission_text,
            submission_id=submission_id,
        )

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=[
                    {
                        "role": "user",
                        "parts": [{"text": (f"{SYSTEM_INSTRUCTIONS}\n\n{prompt}")}],
                    }
                ],
                config={
                    "response_format": {
                        "text": {
                            "mime_type": "application/json",
                            "schema": InsuranceSubmission.model_json_schema(),
                        }
                    }
                },
            )
        except Exception as error:
            raise LLMClientError(f"Gemini request failed for model '{self.model}'.") from error

        if not response.text:
            raise LLMClientError("Gemini returned an empty response.")

        try:
            submission = InsuranceSubmission.model_validate_json(response.text)
        except ValidationError as error:
            raise LLMClientError(
                "Gemini returned a response that failed application validation."
            ) from error

        return submission.model_copy(
            update={
                "submission_id": submission_id,
            }
        )
