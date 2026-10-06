from __future__ import annotations

from google import genai
from google.genai import types
from pydantic import ValidationError

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm.base import LLMClientError, TokenUsage
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
        submission, _ = self.extract_with_usage(submission_text, submission_id)

        return submission

    def extract_with_usage(
        self,
        submission_text: str,
        submission_id: str,
    ) -> tuple[InsuranceSubmission, TokenUsage | None]:
        prompt = build_extraction_prompt(
            submission_text=submission_text,
            submission_id=submission_id,
        )

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTIONS,
                    response_mime_type="application/json",
                    response_json_schema=InsuranceSubmission.model_json_schema(),
                    temperature=0,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True,
                    ),
                ),
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

        return (
            submission.model_copy(update={"submission_id": submission_id}),
            self._usage(response),
        )

    def _usage(self, response: object) -> TokenUsage | None:
        metadata = getattr(response, "usage_metadata", None)

        if metadata is None:
            return None

        return TokenUsage(
            provider=self.provider,
            model=self.model,
            input_tokens=int(getattr(metadata, "prompt_token_count", None) or 0),
            output_tokens=int(getattr(metadata, "candidates_token_count", None) or 0)
            + int(getattr(metadata, "thoughts_token_count", None) or 0),
        )
