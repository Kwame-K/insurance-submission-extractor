from __future__ import annotations

from groq import Groq
from pydantic import ValidationError

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm.base import LLMClientError
from insurance_submission_extractor.prompts import (
    SYSTEM_INSTRUCTIONS,
    build_extraction_prompt,
)
from insurance_submission_extractor.schemas import InsuranceSubmission


class GroqClient:
    provider = "groq"

    def __init__(self, settings: Settings) -> None:
        if settings.groq_api_key is None:
            raise LLMClientError("GROQ_API_KEY is required when using the Groq provider.")

        self.model = settings.groq_model
        self._client = Groq(
            api_key=settings.groq_api_key.get_secret_value(),
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
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_INSTRUCTIONS,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "insurance_submission",
                        "strict": False,
                        "schema": InsuranceSubmission.model_json_schema(),
                    },
                },
            )
        except Exception as error:
            raise LLMClientError(f"Groq request failed for model '{self.model}'.") from error

        content = response.choices[0].message.content

        if not content:
            raise LLMClientError("Groq returned an empty response.")

        try:
            submission = InsuranceSubmission.model_validate_json(content)
        except ValidationError as error:
            raise LLMClientError(
                "Groq returned a response that failed application validation."
            ) from error

        return submission.model_copy(
            update={
                "submission_id": submission_id,
            }
        )
