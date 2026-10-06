from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm import LLMClientError
from insurance_submission_extractor.persistence import (
    DatabaseStore,
    create_store,
    normalize_database_url,
)
from insurance_submission_extractor.persistence.models import Base, EvaluationCaseRow
from insurance_submission_extractor.schemas import CoverageType, InsuranceSubmission, ProductLine
from insurance_submission_extractor.services import SubmissionExtractor
from insurance_submission_extractor.services.telemetry import summarize_records

TEXT = (
    "Le Jardin Bistro is a restaurant in Montreal, QC H2X 1Y4. Built in 1998. "
    "It has 24 employees and annual revenue of CAD 1,200,000. "
    "We are seeking commercial property and business interruption coverage."
)


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.provider = "gemini"
        self.model = "gemini-model"
        self.fail = fail

    def extract_submission(self, submission_text: str, submission_id: str) -> InsuranceSubmission:
        if self.fail:
            raise LLMClientError("Provider is unavailable.")
        return InsuranceSubmission(
            submission_id=submission_id,
            product_line=ProductLine.COMMERCIAL_PROPERTY,
            insured_name="Le Jardin Bistro",
            business_activity="restaurant",
            location_city="Montreal",
            location_province="QC",
            postal_code="H2X 1Y4",
            building_construction_year=1998,
            employee_count=24,
            annual_revenue_cad=1_200_000,
            requested_coverages=[CoverageType.PROPERTY_DAMAGE],
        )


@pytest.fixture
def store() -> DatabaseStore:
    database = DatabaseStore("sqlite://")
    yield database
    database.close()


def evaluation_report() -> dict:
    def case(case_id: str, passed: bool) -> dict:
        return {
            "case_id": case_id,
            "duration_ms": 120.5,
            "evaluation": {
                "case_id": case_id,
                "passed": passed,
                "checks": {"field:insured_name": passed},
                "failures": [] if passed else ["insured_name: expected 'A', got 'B'"],
                "hallucinated_fields": [],
            },
            "result": {"submission": {"insured_name": "SECRET NAME"}},
        }

    return {
        "provider": "gemini",
        "model": "gemini-model",
        "evaluated_at": "2026-10-06T12:00:00+00:00",
        "dataset": "data/golden/insurance_submission_cases_v2.jsonl",
        "summary": {
            "total_cases": 2,
            "passed_cases": 1,
            "failed_cases": 1,
            "pass_rate": 0.5,
            "errored_cases": 0,
            "by_family": {"base": {"total": 1}, "multi_site": {"total": 1}},
        },
        "field_metrics": {
            "missing_field_recall": 1.0,
            "hallucination": {"rate": 0.0},
            "fields": {"insured_name": {"correct": 1, "total": 2, "accuracy": 0.5}},
        },
        "cases": [case("case_001", True), case("gen_multi_site_0001", False)],
    }


def test_migration_creates_schema_that_matches_the_models(store: DatabaseStore) -> None:
    store.migrate()
    store.migrate()

    tables = set(inspect(store.engine).get_table_names())
    assert {"extraction_runs", "evaluation_runs", "evaluation_cases"} <= tables

    with store.engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert differences == []


def test_extraction_is_stored_and_read_back_in_log_shape(store: DatabaseStore) -> None:
    SubmissionExtractor(FakeClient(), extraction_store=store).extract(TEXT, "DB-1")

    records = store.extraction_records()

    assert len(records) == 1
    assert records[0]["submission_id"] == "DB-1"
    assert records[0]["status"] == "ok"
    assert summarize_records(records)["total_extractions"] == 1


def test_failed_extraction_is_stored_with_error_type(store: DatabaseStore) -> None:
    with pytest.raises(LLMClientError):
        SubmissionExtractor(FakeClient(fail=True), extraction_store=store).extract(TEXT, "DB-2")

    record = store.extraction_records()[0]

    assert record["status"] == "error"
    assert record["error_type"] == "LLMClientError"


def test_database_holds_no_submission_content(store: DatabaseStore) -> None:
    SubmissionExtractor(FakeClient(), extraction_store=store).extract(TEXT, "DB-3")
    store.save_evaluation(evaluation_report())

    with store.engine.connect() as connection:
        dump = "\n".join(connection.connection.iterdump())

    for secret in ("Le Jardin Bistro", "H2X 1Y4", "SECRET NAME", "1,200,000"):
        assert secret not in dump


def test_unreachable_database_never_breaks_extraction(tmp_path: Path) -> None:
    broken = DatabaseStore(f"sqlite:///{tmp_path}/missing_directory/history.db")

    result = SubmissionExtractor(FakeClient(), extraction_store=broken).extract(TEXT, "DB-4")

    assert result.submission.insured_name == "Le Jardin Bistro"


def test_evaluation_report_is_stored_with_cases_and_families(store: DatabaseStore) -> None:
    run_id = store.save_evaluation(evaluation_report())

    runs = store.evaluation_runs()
    assert [run["id"] for run in runs] == [run_id]
    assert runs[0]["pass_rate"] == 0.5
    assert runs[0]["hallucination_rate"] == 0.0

    with Session(store.engine) as session:
        rows = session.scalars(select(EvaluationCaseRow).order_by(EvaluationCaseRow.id)).all()
        assert [(row.case_id, row.family, row.passed) for row in rows] == [
            ("case_001", "base", True),
            ("gen_multi_site_0001", "multi_site", False),
        ]
        assert rows[1].failures == ["insured_name: expected 'A', got 'B'"]


def test_deleting_an_evaluation_run_removes_its_cases(store: DatabaseStore) -> None:
    run_id = store.save_evaluation(evaluation_report())

    with store.engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(text("DELETE FROM evaluation_runs WHERE id = :id"), {"id": run_id})

    with Session(store.engine) as session:
        assert session.scalars(select(EvaluationCaseRow)).all() == []


def test_postgresql_urls_use_the_psycopg_driver() -> None:
    assert normalize_database_url("postgresql://u:p@db:5432/app") == (
        "postgresql+psycopg://u:p@db:5432/app"
    )
    assert normalize_database_url("postgres://u@db/app") == "postgresql+psycopg://u@db/app"
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"


def test_store_is_off_without_a_database_url() -> None:
    assert create_store(Settings(_env_file=None, database_url="")) is None
    assert create_store(Settings(_env_file=None)) is None
    assert isinstance(
        create_store(Settings(_env_file=None, database_url="sqlite://")), DatabaseStore
    )
