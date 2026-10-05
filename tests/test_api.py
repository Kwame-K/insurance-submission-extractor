from fastapi.testclient import TestClient

from insurance_submission_extractor.api.app import create_app
from insurance_submission_extractor.llm import LLMClientError
from insurance_submission_extractor.schemas import (
    CoverageType,
    InsuranceSubmission,
    ProductLine,
)
from insurance_submission_extractor.services import SubmissionExtractor

SOURCE_TEXT = (
    "We are seeking commercial property and business interruption coverage for a "
    "restaurant in Montreal, QC H2X 1Y4. The building was constructed in 1998. "
    "The restaurant has 24 employees and annual revenue of CAD 1,200,000."
)


class FakeLLMClient:
    provider = "fake"
    model = "fake-model"

    def extract_submission(
        self,
        submission_text: str,
        submission_id: str,
    ) -> InsuranceSubmission:
        return InsuranceSubmission(
            submission_id=submission_id,
            product_line=ProductLine.COMMERCIAL_PROPERTY,
            business_activity="Restaurant",
            location_city="Montreal",
            location_province="QC",
            postal_code="H2X 1Y4",
            building_construction_year=1998,
            occupancy_type="Restaurant",
            employee_count=24,
            annual_revenue_cad=1_200_000,
            requested_coverages=[
                CoverageType.PROPERTY_DAMAGE,
                CoverageType.BUSINESS_INTERRUPTION,
            ],
        )


class FailingLLMClient:
    provider = "failing"
    model = "failing-model"

    def extract_submission(
        self,
        submission_text: str,
        submission_id: str,
    ) -> InsuranceSubmission:
        raise LLMClientError("Provider is unavailable.")


def create_test_client(extractor: SubmissionExtractor) -> TestClient:
    app = create_app()
    app.state.extractor = extractor
    return TestClient(app)


def valid_payload() -> dict[str, str]:
    return {
        "source_id": "SRC-BROKER-EMAIL-001",
        "source_type": "BROKER_EMAIL",
        "document_name": "restaurant-submission.txt",
        "content": SOURCE_TEXT,
        "language": "en",
    }


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["correlation_id"] == response.headers["X-Correlation-ID"]


def test_extract_submission_returns_complete_http_contract() -> None:
    client = create_test_client(SubmissionExtractor(FakeLLMClient()))

    response = client.post("/v1/extract-submission", json=valid_payload())

    assert response.status_code == 200

    payload = response.json()

    assert payload["source_id"] == "SRC-BROKER-EMAIL-001"
    assert payload["extraction_status"] == "COMPLETE"
    assert payload["missing_fields"] == []
    assert payload["ambiguous_fields"] == []
    assert payload["submission_data"]["submission_id"] == "SRC-BROKER-EMAIL-001"
    assert payload["submission_data"]["location_province"] == "QC"
    assert payload["review_required"] is False
    assert {ref["field_name"] for ref in payload["source_references"]} >= {
        "location_province",
        "postal_code",
        "annual_revenue_cad",
    }
    assert payload["provider"] == "fake"
    assert payload["model"] == "fake-model"
    assert payload["processed_at"] is not None
    assert payload["data_quality_flags"] == [
        {
            "field": "claims_history",
            "severity": "info",
            "code": "CLAIMS_HISTORY_NOT_PROVIDED",
            "message": "No claims history was provided in the submission.",
        }
    ]


def test_extract_submission_rejects_invalid_payload() -> None:
    client = TestClient(create_app())

    invalid_payload = valid_payload()
    invalid_payload["unexpected_field"] = "must fail"

    response = client.post("/v1/extract-submission", json=invalid_payload)

    assert response.status_code == 422


def test_extract_submission_returns_bad_gateway_when_provider_fails() -> None:
    client = create_test_client(SubmissionExtractor(FailingLLMClient()))

    response = client.post("/v1/extract-submission", json=valid_payload())

    assert response.status_code == 502

    payload = response.json()

    assert payload["detail"]["source_id"] == "SRC-BROKER-EMAIL-001"
    assert payload["detail"]["error_code"] == "LLM_PROVIDER_ERROR"
    assert payload["detail"]["error_message"] == "Provider is unavailable."


def test_health_returns_provided_correlation_id() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/health",
        headers={"X-Correlation-ID": "workflow-2026-0001"},
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "workflow-2026-0001"
    assert response.json()["correlation_id"] == "workflow-2026-0001"


def test_health_generates_correlation_id_when_missing() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"]
    assert response.json()["correlation_id"] == response.headers["X-Correlation-ID"]


def test_extraction_returns_provided_correlation_id() -> None:
    client = create_test_client(SubmissionExtractor(FakeLLMClient()))

    response = client.post(
        "/v1/extract-submission",
        json=valid_payload(),
        headers={"X-Correlation-ID": "workflow-2026-0002"},
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "workflow-2026-0002"


def test_unsupported_value_is_flagged_for_review() -> None:
    class InferringLLMClient(FakeLLMClient):
        def extract_submission(
            self, submission_text: str, submission_id: str
        ) -> InsuranceSubmission:
            return (
                super()
                .extract_submission(submission_text, submission_id)
                .model_copy(update={"location_province": "ON"})
            )

    client = create_test_client(SubmissionExtractor(InferringLLMClient()))
    payload = client.post("/v1/extract-submission", json=valid_payload()).json()

    assert payload["ambiguous_fields"] == ["location_province"]
    assert payload["review_required"] is True
    assert any(f["code"] == "VALUE_NOT_FOUND_IN_SOURCE" for f in payload["data_quality_flags"])
