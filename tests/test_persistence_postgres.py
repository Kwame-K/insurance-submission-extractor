"""PostgreSQL checks for the persistence layer.

Skipped unless TEST_POSTGRES_URL points at a disposable database, for example:
    TEST_POSTGRES_URL=postgresql://postgres:dev@localhost:5432/extractor
The tables are dropped before and after each test.
"""

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from insurance_submission_extractor.persistence import DatabaseStore
from insurance_submission_extractor.persistence.models import Base
from insurance_submission_extractor.services.telemetry import (
    ExtractionLogRecord,
    summarize_records,
)

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is not set")

TABLES = ("evaluation_cases", "evaluation_runs", "extraction_runs", "alembic_version")


def drop_tables(store: DatabaseStore) -> None:
    with store.engine.begin() as connection:
        for table in TABLES:
            connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))


@pytest.fixture
def store():
    database = DatabaseStore(POSTGRES_URL)
    drop_tables(database)
    yield database
    drop_tables(database)
    database.close()


def test_migration_creates_the_schema_on_postgresql(store: DatabaseStore) -> None:
    store.migrate()
    store.migrate()

    assert {"extraction_runs", "evaluation_runs", "evaluation_cases"} <= set(
        inspect(store.engine).get_table_names()
    )
    with store.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_extraction_and_evaluation_round_trip_on_postgresql(store: DatabaseStore) -> None:
    store.save_extraction(
        ExtractionLogRecord(
            submission_id="PG-1",
            status="ok",
            provider="gemini",
            model="gemini-model",
            duration_ms=12.5,
            unsupported_fields=["annual_revenue_cad"],
            llm_calls=1,
            failed_llm_calls=0,
        )
    )
    run_id = store.save_evaluation(
        {
            "provider": "gemini",
            "model": "gemini-model",
            "evaluated_at": "2026-10-06T12:00:00+00:00",
            "dataset": "data/golden/insurance_submission_cases_v2.jsonl",
            "summary": {
                "total_cases": 1,
                "passed_cases": 1,
                "failed_cases": 0,
                "pass_rate": 1.0,
                "errored_cases": 0,
                "by_family": {"base": {"total": 1}},
            },
            "field_metrics": {"missing_field_recall": 1.0, "hallucination": {"rate": 0.0}},
            "cases": [
                {
                    "case_id": "restaurant_complete",
                    "duration_ms": 10.0,
                    "evaluation": {"passed": True, "checks": {"field:x": True}, "failures": []},
                }
            ],
        }
    )

    records = store.extraction_records()
    assert records[0]["unsupported_fields"] == ["annual_revenue_cad"]
    assert summarize_records(records)["total_extractions"] == 1
    assert store.evaluation_runs()[0]["id"] == run_id

    with store.engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM evaluation_cases")).scalar_one()
    assert count == 1
