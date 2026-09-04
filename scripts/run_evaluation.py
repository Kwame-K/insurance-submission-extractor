from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from insurance_submission_extractor.config import LLMProvider, Settings
from insurance_submission_extractor.evaluation import (
    CaseEvaluation,
    GoldenCase,
    evaluate_extraction_result,
    load_golden_cases,
)
from insurance_submission_extractor.llm import create_llm_client
from insurance_submission_extractor.services import SubmissionExtractor

DEFAULT_DATASET_PATH = Path("data/golden/insurance_submission_cases.jsonl")
DEFAULT_OUTPUT_DIRECTORY = Path("data/evaluations")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run insurance submission extraction evaluation cases against an LLM provider."
        )
    )

    parser.add_argument(
        "--provider",
        choices=[provider.value for provider in LLMProvider],
        required=True,
        help="LLM provider to evaluate.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to the JSONL golden dataset.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="Directory where the evaluation report will be written.",
    )

    return parser


def evaluate_case(
    extractor: SubmissionExtractor,
    golden_case: GoldenCase,
) -> tuple[CaseEvaluation, dict[str, object]]:
    submission_text = Path(golden_case.input_file).read_text(encoding="utf-8")

    started_at = perf_counter()

    result = extractor.extract(
        submission_text=submission_text,
        submission_id=golden_case.case_id,
    )

    duration_ms = round(
        (perf_counter() - started_at) * 1000,
        2,
    )

    evaluation = evaluate_extraction_result(
        result=result,
        golden_case=golden_case,
    )

    return evaluation, {
        "case_id": golden_case.case_id,
        "duration_ms": duration_ms,
        "evaluation": evaluation.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
    }


def main() -> None:
    parser = build_parser()
    arguments = parser.parse_args()

    settings = Settings(
        llm_provider=arguments.provider,
    )
    llm_client = create_llm_client(settings)
    extractor = SubmissionExtractor(llm_client)

    golden_cases = load_golden_cases(arguments.dataset)

    case_reports: list[dict[str, object]] = []

    for golden_case in golden_cases:
        evaluation, case_report = evaluate_case(
            extractor=extractor,
            golden_case=golden_case,
        )
        case_reports.append(case_report)

        status = "PASS" if evaluation.passed else "FAIL"

        print(f"[{status}] {golden_case.case_id} ({case_report['duration_ms']} ms)")

        for failure in evaluation.failures:
            print(f"  - {failure}")

    passed_cases = sum(case_report["evaluation"]["passed"] for case_report in case_reports)
    total_cases = len(case_reports)

    report = {
        "provider": llm_client.provider,
        "model": llm_client.model,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "dataset": str(arguments.dataset),
        "summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": total_cases - passed_cases,
            "pass_rate": round(passed_cases / total_cases, 4),
        },
        "cases": case_reports,
    }

    arguments.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    output_path = arguments.output_directory / (f"{llm_client.provider}_{timestamp}.json")

    output_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"Summary: {passed_cases}/{total_cases} cases passed ({report['summary']['pass_rate']:.1%})"
    )
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
