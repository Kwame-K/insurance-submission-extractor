from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from insurance_submission_extractor.schemas import ExtractionResult


class GoldenCase(BaseModel):
    case_id: str
    input_file: str
    expected_fields: dict[str, Any] = Field(default_factory=dict)
    acceptable_field_values: dict[str, list[Any]] = Field(default_factory=dict)
    expected_missing_fields: list[str] = Field(default_factory=list)
    expected_flag_codes: list[str] = Field(default_factory=list)
    expected_review_required: bool
    expected_claim_years: list[int] | None = None


class CaseEvaluation(BaseModel):
    case_id: str
    passed: bool
    checks: dict[str, bool]
    failures: list[str] = Field(default_factory=list)
    hallucinated_fields: list[str] = Field(default_factory=list)


def values_match(actual: Any, expected: Any, *, casefold: bool = False) -> bool:
    """Compare golden values while treating equivalent Unicode text as equal."""
    if isinstance(actual, str) and isinstance(expected, str):
        left = unicodedata.normalize("NFC", actual).strip()
        right = unicodedata.normalize("NFC", expected).strip()
        return left.casefold() == right.casefold() if casefold else left == right
    if (
        isinstance(actual, list)
        and isinstance(expected, list)
        and all(isinstance(item, str) for item in [*actual, *expected])
    ):
        return sorted(actual) == sorted(expected)
    return actual == expected


def load_golden_cases(dataset_path: Path) -> list[GoldenCase]:
    cases: list[GoldenCase] = []

    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        stripped_line = line.strip()

        if not stripped_line:
            continue

        cases.append(GoldenCase.model_validate_json(stripped_line))

    return cases


def evaluate_extraction_result(
    result: ExtractionResult,
    golden_case: GoldenCase,
) -> CaseEvaluation:
    submission_data = result.submission.model_dump(mode="json")
    checks: dict[str, bool] = {}
    failures: list[str] = []

    for field_name, expected_value in golden_case.expected_fields.items():
        actual_value = submission_data.get(field_name)
        check_name = f"field:{field_name}"
        checks[check_name] = values_match(actual_value, expected_value)

        if not checks[check_name]:
            failures.append(f"{field_name}: expected {expected_value!r}, got {actual_value!r}")

    for field_name, acceptable_values in golden_case.acceptable_field_values.items():
        actual_value = submission_data.get(field_name)
        check_name = f"acceptable_field:{field_name}"
        checks[check_name] = any(
            values_match(actual_value, value, casefold=True) for value in acceptable_values
        )

        if not checks[check_name]:
            failures.append(
                f"{field_name}: expected one of {acceptable_values!r}, got {actual_value!r}"
            )

    for field_name in golden_case.expected_missing_fields:
        check_name = f"missing_field:{field_name}"
        checks[check_name] = field_name in result.missing_fields

        if not checks[check_name]:
            failures.append(f"{field_name}: expected to be listed in missing_fields")

    actual_flag_codes = {flag.code for flag in result.data_quality_flags}

    for expected_flag_code in golden_case.expected_flag_codes:
        check_name = f"flag:{expected_flag_code}"
        checks[check_name] = expected_flag_code in actual_flag_codes

        if not checks[check_name]:
            failures.append(f"{expected_flag_code}: expected data quality flag was not found")

    if golden_case.expected_claim_years is not None:
        actual_years = sorted(claim.year for claim in result.submission.claims_history)
        checks["claims:years"] = actual_years == sorted(golden_case.expected_claim_years)

        if not checks["claims:years"]:
            failures.append(
                f"claims: expected years {sorted(golden_case.expected_claim_years)!r}, "
                f"got {actual_years!r}"
            )

    hallucinated_fields = [
        field_name
        for field_name in golden_case.expected_missing_fields
        if submission_data.get(field_name) not in (None, "", [])
    ]

    checks["review_required"] = result.review_required == golden_case.expected_review_required

    if not checks["review_required"]:
        failures.append(
            "review_required: "
            f"expected {golden_case.expected_review_required!r}, "
            f"got {result.review_required!r}"
        )

    return CaseEvaluation(
        case_id=golden_case.case_id,
        passed=all(checks.values()),
        checks=checks,
        failures=failures,
        hallucinated_fields=hallucinated_fields,
    )


def compute_field_metrics(evaluations: list[CaseEvaluation]) -> dict[str, Any]:
    """Aggregate per-field accuracy, missing-field recall and hallucination rate."""
    totals: dict[str, list[int]] = {}
    probes = 0
    detected = 0

    for evaluation in evaluations:
        for check_name, passed in evaluation.checks.items():
            kind, _, field_name = check_name.partition(":")

            if kind in {"field", "acceptable_field"}:
                counts = totals.setdefault(field_name, [0, 0])
                counts[0] += int(passed)
                counts[1] += 1
            elif kind == "missing_field":
                probes += 1
                detected += int(passed)

    hallucinated = sum(len(evaluation.hallucinated_fields) for evaluation in evaluations)

    return {
        "fields": {
            name: {"correct": correct, "total": total, "accuracy": round(correct / total, 4)}
            for name, (correct, total) in sorted(totals.items())
        },
        "missing_field_recall": round(detected / probes, 4) if probes else None,
        "hallucination": {
            "probes": probes,
            "hallucinated": hallucinated,
            "rate": round(hallucinated / probes, 4) if probes else None,
        },
        "case_pass_rate": (
            round(sum(e.passed for e in evaluations) / len(evaluations), 4) if evaluations else None
        ),
    }
