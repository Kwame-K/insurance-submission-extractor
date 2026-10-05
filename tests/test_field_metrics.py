from insurance_submission_extractor.evaluation import (
    CaseEvaluation,
    GoldenCase,
    compute_field_metrics,
    evaluate_extraction_result,
)
from insurance_submission_extractor.schemas import ExtractionResult, InsuranceSubmission


def make_result(**fields: object) -> ExtractionResult:
    return ExtractionResult(
        submission=InsuranceSubmission(submission_id="X", **fields),
        missing_fields=[],
        data_quality_flags=[],
        extraction_confidence=None,
        extraction_notes=[],
        provider="fake",
        model="fake",
        review_required=False,
    )


def test_hallucinated_field_is_reported_without_changing_pass_status() -> None:
    golden = GoldenCase(
        case_id="c1",
        input_file="x.txt",
        expected_missing_fields=["location_province"],
        expected_review_required=False,
    )
    result = make_result(location_province="QC")
    evaluation = evaluate_extraction_result(result, golden)

    assert evaluation.hallucinated_fields == ["location_province"]


def test_claim_years_are_checked_when_expected() -> None:
    golden = GoldenCase(
        case_id="c2",
        input_file="x.txt",
        expected_claim_years=[2012],
        expected_review_required=False,
    )
    evaluation = evaluate_extraction_result(make_result(), golden)

    assert evaluation.checks["claims:years"] is False


def test_compute_field_metrics_aggregates_accuracy_and_hallucination() -> None:
    evaluations = [
        CaseEvaluation(
            case_id="a",
            passed=True,
            checks={"field:location_city": True, "missing_field:postal_code": True},
        ),
        CaseEvaluation(
            case_id="b",
            passed=False,
            checks={"field:location_city": False, "missing_field:postal_code": False},
            hallucinated_fields=["postal_code"],
        ),
    ]
    metrics = compute_field_metrics(evaluations)

    assert metrics["fields"]["location_city"]["accuracy"] == 0.5
    assert metrics["missing_field_recall"] == 0.5
    assert metrics["hallucination"] == {"probes": 2, "hallucinated": 1, "rate": 0.5}
    assert metrics["case_pass_rate"] == 0.5


def test_values_match_ignores_unicode_composition_and_optional_case() -> None:
    from insurance_submission_extractor.evaluation import values_match

    assert values_match("Lt\u00e9e", "Lte\u0301e")
    assert not values_match("Ltee", "Lt\u00e9e")
    assert values_match("Clinique Dentaire", "clinique dentaire", casefold=True)
    assert not values_match("Clinique Dentaire", "clinique dentaire")


def test_values_match_ignores_order_of_string_lists() -> None:
    from insurance_submission_extractor.evaluation import values_match

    assert values_match(
        ["business_interruption", "property_damage"], ["property_damage", "business_interruption"]
    )
    assert not values_match(["property_damage"], ["property_damage", "business_interruption"])
