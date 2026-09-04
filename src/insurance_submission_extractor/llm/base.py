from __future__ import annotations

from typing import Protocol

from insurance_submission_extractor.schemas import InsuranceSubmission


class LLMClientError(RuntimeError):
    """Raised when an LLM provider cannot complete a request."""


class LLMClient(Protocol):
    provider: str
    model: str

    def extract_submission(
        self,
        submission_text: str,
        submission_id: str,
    ) -> InsuranceSubmission:
        """Extract a structured insurance submission from unstructured text."""
