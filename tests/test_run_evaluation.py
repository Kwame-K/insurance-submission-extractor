import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from insurance_submission_extractor.llm import LLMClientError
from insurance_submission_extractor.schemas import InsuranceSubmission, ProductLine

ROOT = Path(__file__).resolve().parent.parent


def load_runner():
    path = ROOT / "scripts" / "run_evaluation.py"
    spec = importlib.util.spec_from_file_location("run_evaluation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FlakyClient:
    provider = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def extract_submission(self, submission_text: str, submission_id: str) -> InsuranceSubmission:
        self.calls += 1
        if self.calls == 3:
            raise LLMClientError("rate limited")
        return InsuranceSubmission(
            submission_id=submission_id,
            product_line=ProductLine.COMMERCIAL_PROPERTY,
            location_province="QC",
        )


def test_case_family_parses_generated_ids() -> None:
    runner = load_runner()

    assert runner.case_family("gen_no_geo_03") == "no_geo"
    assert runner.case_family("restaurant_complete") == "base"


def test_runner_survives_provider_errors_and_reports_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = load_runner()
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(runner, "Settings", lambda **kwargs: SimpleNamespace(database_url=None))
    monkeypatch.setattr(runner, "create_llm_client", lambda settings: FlakyClient())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_evaluation.py",
            "--provider",
            "gemini",
            "--dataset",
            "data/golden/insurance_submission_cases.jsonl",
            "--output-directory",
            str(tmp_path),
        ],
    )

    runner.main()

    report = json.loads(next(tmp_path.glob("fake_*.json")).read_text(encoding="utf-8"))
    assert report["summary"]["total_cases"] == 4
    assert report["summary"]["errored_cases"] == 1
    assert "by_family" in report["summary"]
    assert report["field_metrics"]["hallucination"]["probes"] >= 1
    assert report["field_metrics"]["fields"]["location_city"]["total"] >= 1


def test_case_selection_filters_by_id_and_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = load_runner()
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(runner, "Settings", lambda **kwargs: SimpleNamespace(database_url=None))
    monkeypatch.setattr(runner, "create_llm_client", lambda settings: FlakyClient())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_evaluation.py",
            "--provider",
            "gemini",
            "--dataset",
            "data/golden/insurance_submission_cases_v2.jsonl",
            "--output-directory",
            str(tmp_path),
            "--case-id",
            "restaurant_complete",
            "--case-prefix",
            "gen_coverage_phrasing_",
        ],
    )

    runner.main()

    report = json.loads(next(tmp_path.glob("fake_*.json")).read_text(encoding="utf-8"))
    assert report["summary"]["total_cases"] == 7
