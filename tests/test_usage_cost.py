import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm import (
    FallbackLLMClient,
    GeminiClient,
    GroqClient,
    LLMClientError,
    TokenUsage,
)
from insurance_submission_extractor.pricing import ModelPrice, PriceBook
from insurance_submission_extractor.services import SubmissionExtractor
from insurance_submission_extractor.services.telemetry import summarize_records
from tests.test_telemetry import TEXT, FakeClient

PAYLOAD = FakeClient("x").extract_submission(TEXT, "S").model_dump_json()


class UsageClient(FakeClient):
    def __init__(self, provider: str, fail: bool = False, tokens: tuple[int, int] = (1000, 200)):
        super().__init__(provider, fail)
        self.tokens = tokens

    def extract_with_usage(self, submission_text: str, submission_id: str):
        submission = self.extract_submission(submission_text, submission_id)
        usage = TokenUsage(self.provider, self.model, *self.tokens)

        return submission, usage


def settings(**values: object) -> Settings:
    return Settings(_env_file=None, gemini_api_key="k", groq_api_key="k", **values)


def test_gemini_usage_counts_thinking_tokens_as_output() -> None:
    client = GeminiClient(settings())
    metadata = SimpleNamespace(
        prompt_token_count=1200, candidates_token_count=300, thoughts_token_count=500
    )
    response = SimpleNamespace(text=PAYLOAD, usage_metadata=metadata)
    client._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: response))

    _, usage = client.extract_with_usage(TEXT, "S1")

    assert (usage.provider, usage.input_tokens, usage.output_tokens) == ("gemini", 1200, 800)


def test_groq_usage_and_missing_usage() -> None:
    client = GroqClient(settings())
    message = SimpleNamespace(content=PAYLOAD)
    usage = SimpleNamespace(prompt_tokens=900, completion_tokens=450)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)
    completions = SimpleNamespace(create=lambda **_: response)
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    _, counted = client.extract_with_usage(TEXT, "S2")
    response.usage = None
    _, missing = client.extract_with_usage(TEXT, "S2")

    assert (counted.input_tokens, counted.output_tokens) == (900, 450)
    assert missing is None


def test_price_book_computes_cost_and_refuses_unpriced_calls() -> None:
    book = PriceBook({"gemini": ModelPrice(0.5, 3.0)})
    priced = TokenUsage("gemini", "m", 1_000_000, 100_000)
    unpriced = TokenUsage("groq", "m", 10, 10)

    assert book.cost_usd([priced]) == pytest.approx(0.8)
    assert book.cost_usd([priced, unpriced]) is None
    assert book.cost_usd([]) is None


def test_settings_build_price_book_only_from_complete_pairs() -> None:
    book = settings(
        gemini_input_price_per_million_usd=0.5,
        gemini_output_price_per_million_usd=3.0,
        groq_input_price_per_million_usd=0.2,
    ).price_book()

    assert set(book.prices) == {"gemini"}
    assert settings().price_book().prices == {}


def test_extractor_logs_tokens_and_cost(tmp_path: Path) -> None:
    log = tmp_path / "e.jsonl"
    book = PriceBook({"gemini": ModelPrice(1.0, 2.0)})

    SubmissionExtractor(UsageClient("gemini"), log, book).extract(TEXT, "S3")
    record = json.loads(log.read_text())

    assert (record["input_tokens"], record["output_tokens"]) == (1000, 200)
    assert record["cost_usd"] == pytest.approx(0.0014)
    assert record["attempts"] == [
        {"provider": "gemini", "model": "gemini-model", "input_tokens": 1000, "output_tokens": 200}
    ]


def test_unpriced_and_unmetered_calls_have_no_cost(tmp_path: Path) -> None:
    log = tmp_path / "e.jsonl"

    SubmissionExtractor(UsageClient("gemini"), log).extract(TEXT, "S4")
    SubmissionExtractor(FakeClient("gemini"), log).extract(TEXT, "S5")
    unpriced, unmetered = [json.loads(line) for line in log.read_text().splitlines()]

    assert unpriced["input_tokens"] == 1000 and unpriced["cost_usd"] is None
    assert unmetered["input_tokens"] is None and unmetered["attempts"] == []


def test_fallback_after_omitted_field_sums_both_attempts(tmp_path: Path) -> None:
    class OmittingClient(UsageClient):
        def extract_submission(self, submission_text: str, submission_id: str):
            submission = super().extract_submission(submission_text, submission_id)

            return submission.model_copy(update={"employee_count": None})

    log = tmp_path / "e.jsonl"
    primary = OmittingClient("gemini", tokens=(1000, 0))
    fallback = UsageClient("groq", tokens=(500, 100))
    book = PriceBook({"gemini": ModelPrice(1.0, 1.0), "groq": ModelPrice(2.0, 2.0)})

    SubmissionExtractor(FallbackLLMClient(primary, fallback), log, book).extract(TEXT, "S6")
    record = json.loads(log.read_text())

    assert record["fallback_used"] is True
    assert [a["provider"] for a in record["attempts"]] == ["gemini", "groq"]
    assert record["input_tokens"] == 1500
    assert record["output_tokens"] == 100
    assert record["cost_usd"] == pytest.approx(0.0022)


def test_fallback_after_primary_error_reports_only_fallback_usage(tmp_path: Path) -> None:
    log = tmp_path / "e.jsonl"
    client = FallbackLLMClient(
        UsageClient("gemini", fail=True), UsageClient("groq", tokens=(500, 100))
    )

    SubmissionExtractor(client, log).extract(TEXT, "S7")
    record = json.loads(log.read_text())

    assert [a["provider"] for a in record["attempts"]] == ["groq"]
    assert record["fallback_used"] is True


def test_failed_extraction_has_no_usage(tmp_path: Path) -> None:
    log = tmp_path / "e.jsonl"

    with pytest.raises(LLMClientError):
        SubmissionExtractor(UsageClient("gemini", fail=True), log).extract(TEXT, "S8")

    assert json.loads(log.read_text())["input_tokens"] is None


def test_summary_reports_tokens_and_cost() -> None:
    base = {
        "event": "extraction",
        "status": "ok",
        "model": "m",
        "provider": "gemini",
        "duration_ms": 1,
    }
    records = [
        {**base, "input_tokens": 1000, "output_tokens": 200, "cost_usd": 0.002},
        {**base, "input_tokens": 3000, "output_tokens": 400, "cost_usd": 0.004},
        {**base, "input_tokens": 500, "output_tokens": 50, "cost_usd": None},
        {**base},
    ]
    summary = summarize_records(records)

    assert summary["tokens"]["extractions_with_usage"] == 3
    assert summary["tokens"]["input_total"] == 4500
    assert summary["tokens"]["output_mean"] == pytest.approx(216.7, abs=0.1)
    assert summary["cost_usd"] == {
        "priced_extractions": 2,
        "unpriced_extractions": 1,
        "total": 0.006,
        "mean_per_extraction": 0.003,
    }


def calls_of(log: Path) -> list[tuple[int, int]]:
    records = [json.loads(line) for line in log.read_text().splitlines()]

    return [(r["llm_calls"], r["failed_llm_calls"]) for r in records]


def test_single_client_counts_one_call(tmp_path: Path) -> None:
    log = tmp_path / "e.jsonl"

    SubmissionExtractor(FakeClient("gemini"), log).extract(TEXT, "C1")
    with pytest.raises(LLMClientError):
        SubmissionExtractor(FakeClient("gemini", fail=True), log).extract(TEXT, "C2")

    assert calls_of(log) == [(1, 0), (1, 1)]


def test_fallback_after_primary_error_counts_two_calls(tmp_path: Path) -> None:
    log = tmp_path / "e.jsonl"
    client = FallbackLLMClient(FakeClient("gemini", fail=True), FakeClient("groq"))

    SubmissionExtractor(client, log).extract(TEXT, "C3")

    assert calls_of(log) == [(2, 1)]


def test_all_providers_failing_counts_both_failed_calls(tmp_path: Path) -> None:
    log = tmp_path / "e.jsonl"
    client = FallbackLLMClient(FakeClient("gemini", fail=True), FakeClient("groq", fail=True))

    with pytest.raises(LLMClientError, match="All providers failed"):
        SubmissionExtractor(client, log).extract(TEXT, "C4")

    assert calls_of(log) == [(2, 2)]


def test_omitted_field_with_failing_fallback_counts_failed_second_call(tmp_path: Path) -> None:
    class OmittingClient(FakeClient):
        def extract_submission(self, submission_text: str, submission_id: str):
            submission = super().extract_submission(submission_text, submission_id)

            return submission.model_copy(update={"employee_count": None})

    log = tmp_path / "e.jsonl"
    client = FallbackLLMClient(OmittingClient("gemini"), FakeClient("groq", fail=True))

    result = SubmissionExtractor(client, log).extract(TEXT, "C5")

    assert result.review_required is True
    assert calls_of(log) == [(2, 1)]


def test_summary_reports_call_counts() -> None:
    base = {"event": "extraction", "model": "m", "provider": "gemini", "duration_ms": 1}
    records = [
        {**base, "status": "ok", "llm_calls": 1, "failed_llm_calls": 0},
        {**base, "status": "ok", "llm_calls": 2, "failed_llm_calls": 1},
        {**base, "status": "error", "llm_calls": 2, "failed_llm_calls": 2},
        {**base, "status": "ok"},
    ]

    assert summarize_records(records)["llm_calls"] == {
        "total": 5,
        "failed": 3,
        "mean_per_extraction": 1.667,
        "max_per_extraction": 2,
    }
