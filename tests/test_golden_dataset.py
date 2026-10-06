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
        "number_formats",
        "partial_address",
        "accented_city",
        "ambiguous_activity",
        "multi_site",
    } <= families


def test_edge_case_family_counts_and_labels() -> None:
    cases = load_golden_cases(DATASET)
    edge_families = (
        "number_formats",
        "partial_address",
        "accented_city",
        "ambiguous_activity",
        "multi_site",
    )
    by_family = {
        family: [case for case in cases if family in case.case_id] for family in edge_families
    }

    assert {family: len(cases) for family, cases in by_family.items()} == {
        "number_formats": 7,
        "partial_address": 6,
        "accented_city": 3,
        "ambiguous_activity": 4,
        "multi_site": 4,
    }
    assert all(
        case.expected_fields.get("source_language") == "fr"
        for case in by_family["number_formats"][:4]
    )
    assert all(
        "location_city" not in case.expected_fields for case in by_family["partial_address"][:4]
    )


def test_multi_site_cases_preserve_first_site_as_the_oracle() -> None:
    for case in load_golden_cases(DATASET):
        if "multi_site" not in case.case_id:
            continue
        text = (ROOT / case.input_file).read_text(encoding="utf-8")
        assert "second location" in text.lower() or "deuxième site" in text.lower()
        assert case.expected_fields["location_city"] in text


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
