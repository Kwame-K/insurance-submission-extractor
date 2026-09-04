from insurance_submission_extractor.evaluation import (
    GoldenCase,
    evaluate_extraction_result,
)
from insurance_submission_extractor.schemas import (
    ClaimsHistoryStatus,
    ExtractionResult,
    InsuranceSubmission,
    ProductLine,
)


def build_result(
    *,
    product_line: ProductLine = ProductLine.CYBER,
    review_required: bool = False,
) -> ExtractionResult:
    return ExtractionResult(
        submission=InsuranceSubmission(
            submission_id="test-case",
            product_line=product_line,
            business_activity="data consulting firm",
            location_city="Montreal",
            location_province="QC",
            postal_code="H3B 2Y5",
            employee_count=35,
            annual_revenue_cad=4_200_000,
            claims_history_status=ClaimsHistoryStatus.NO_LOSSES_REPORTED,
        ),
        review_required=review_required,
        provider="fake",
        model="fake-model",
    )


def test_evaluation_passes_when_result_matches_golden_case() -> None:
    result = build_result()

    golden_case = GoldenCase(
        case_id="cyber_no_losses",
        input_file="data/synthetic/cyber_submission.txt",
        expected_fields={
            "product_line": "cyber",
            "business_activity": "data consulting firm",
            "claims_history_status": "no_losses_reported",
        },
        expected_review_required=False,
    )

    evaluation = evaluate_extraction_result(
        result=result,
        golden_case=golden_case,
    )

    assert evaluation.passed is True
    assert evaluation.failures == []


def test_evaluation_fails_when_expected_field_is_missing() -> None:
    result = build_result()

    golden_case = GoldenCase(
        case_id="cyber_no_losses",
        input_file="data/synthetic/cyber_submission.txt",
        expected_fields={
            "business_activity": "data consulting firm",
        },
        expected_missing_fields=[
            "building_construction_year",
        ],
        expected_review_required=False,
    )

    evaluation = evaluate_extraction_result(
        result=result,
        golden_case=golden_case,
    )

    assert evaluation.passed is False
    assert any("building_construction_year" in failure for failure in evaluation.failures)


def test_evaluation_accepts_allowed_field_normalization() -> None:
    result = build_result()

    golden_case = GoldenCase(
        case_id="cyber_no_losses",
        input_file="data/synthetic/cyber_submission.txt",
        acceptable_field_values={
            "business_activity": [
                "data consulting firm",
                "data consulting",
            ],
        },
        expected_review_required=False,
    )

    evaluation = evaluate_extraction_result(
        result=result,
        golden_case=golden_case,
    )

    assert evaluation.passed is True
    assert evaluation.failures == []
