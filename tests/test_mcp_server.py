from insurance_submission_extractor.mcp_server import server
from insurance_submission_extractor.schemas import CoverageType, InsuranceSubmission, ProductLine
from insurance_submission_extractor.services import SubmissionExtractor


class FakeLLMClient:
    provider = "fake"
    model = "fake-model"

    def extract_submission(self, submission_text: str, submission_id: str) -> InsuranceSubmission:
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
            requested_coverages=[CoverageType.PROPERTY_DAMAGE],
        )


def test_extract_submission_returns_http_contract(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_extractor", lambda: SubmissionExtractor(FakeLLMClient()))
    output = server.extract_submission(
        source_id="SRC-MCP-001",
        content="Please quote insurance for our Montreal restaurant.",
        source_type="BROKER_EMAIL",
        document_name="request.txt",
    )
    assert output["source_id"] == "SRC-MCP-001"
    assert output["extraction_status"] == "COMPLETE"
    assert output["submission_data"]["product_line"] == "commercial_property"
    assert output["provider"] == "fake"
    assert output["model"] == "fake-model"
