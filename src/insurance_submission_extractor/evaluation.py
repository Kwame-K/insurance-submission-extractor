from __future__ import annotations

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


class CaseEvaluation(BaseModel):
    case_id: str
    passed: bool
    checks: dict[str, bool]
    failures: list[str] = Field(default_factory=list)


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
        checks[check_name] = actual_value == expected_value

        if not checks[check_name]:
            failures.append(f"{field_name}: expected {expected_value!r}, got {actual_value!r}")

    for field_name, acceptable_values in golden_case.acceptable_field_values.items():
        actual_value = submission_data.get(field_name)
        check_name = f"acceptable_field:{field_name}"
        checks[check_name] = actual_value in acceptable_values

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
    )
