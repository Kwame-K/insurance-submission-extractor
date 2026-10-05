from pathlib import Path

import pytest

from insurance_submission_extractor.evaluation import load_golden_cases
from tests.evaluation_helpers import load_generator

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data/golden/insurance_submission_cases_v2.jsonl"
generator = load_generator()


def test_dataset_is_large_and_unique() -> None:
    cases = load_golden_cases(DATASET)
    ids = [case.case_id for case in cases]

    assert len(cases) >= 60
    assert len(ids) == len(set(ids))


def test_every_case_has_a_non_empty_input_file() -> None:
    for case in load_golden_cases(DATASET):
        path = ROOT / case.input_file
        assert path.is_file(), case.case_id
        assert path.read_text(encoding="utf-8").strip(), case.case_id


def test_dataset_covers_scenario_families() -> None:
    families = {
        case.case_id.removeprefix("gen_").rsplit("_", 1)[0]
        for case in load_golden_cases(DATASET)
        if case.case_id.startswith("gen_")
    }

    assert {
        "complete",
        "french",
        "no_geo",
        "no_coverage",
        "claims_reported",
        "claim_before_build",
        "zero_revenue",
        "zero_employees",
        "noisy_distractors",
    } <= families


def test_inconsistent_cases_raise_expected_flag() -> None:
    cases = [c for c in load_golden_cases(DATASET) if "claim_before_build" in c.case_id]

    assert cases
    assert all("BUILDING_YEAR_AFTER_CLAIM" in c.expected_flag_codes for c in cases)


def test_no_coverage_cases_expect_missing_coverages() -> None:
    cases = [c for c in load_golden_cases(DATASET) if "no_coverage" in c.case_id]

    assert cases
    assert all("requested_coverages" in c.expected_missing_fields for c in cases)


def test_committed_dataset_matches_generator(tmp_path: Path) -> None:
    out_dir = tmp_path / "generated"
    dataset = tmp_path / "dataset.jsonl"
    generator.generate(out_dir, dataset, ROOT / "data/golden/insurance_submission_cases.jsonl")

    assert dataset.read_text(encoding="utf-8") == DATASET.read_text(encoding="utf-8")
    for generated in out_dir.glob("gen_*.txt"):
        committed = ROOT / "data/synthetic/generated" / generated.name
        assert committed.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8")


@pytest.mark.parametrize("scenario", ["no_geo", "no_year"])
def test_missing_field_cases_never_leak_values_into_expected_fields(scenario: str) -> None:
    for case in load_golden_cases(DATASET):
        if scenario in case.case_id:
            for field_name in case.expected_missing_fields:
                assert field_name not in case.expected_fields
