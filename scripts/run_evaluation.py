from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from insurance_submission_extractor.config import LLMProvider, Settings
from insurance_submission_extractor.evaluation import (
    CaseEvaluation,
    GoldenCase,
    compute_field_metrics,
    evaluate_extraction_result,
    load_golden_cases,
)
from insurance_submission_extractor.llm import LLMClientError, create_llm_client
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

    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Pause between cases to respect provider rate limits.",
    )
    parser.add_argument(
        "--fallback-provider",
        choices=[provider.value for provider in LLMProvider],
        default=None,
        help="Evaluate the combined primary + fallback system instead of one provider.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Evaluate only this case ID. Repeat the option for multiple cases.",
    )
    parser.add_argument(
        "--case-prefix",
        action="append",
        default=[],
        help="Evaluate case IDs beginning with this prefix. Repeat for multiple prefixes.",
    )

    return parser


def case_family(case_id: str) -> str:
    """Return the scenario family of a generated case id, or the id itself."""
    if case_id.startswith("gen_"):
        return case_id.removeprefix("gen_").rsplit("_", 1)[0]
    return "base"


def summarize_by_family(evaluations: list[CaseEvaluation]) -> dict[str, dict[str, object]]:
    families: dict[str, list[CaseEvaluation]] = {}
    for evaluation in evaluations:
        families.setdefault(case_family(evaluation.case_id), []).append(evaluation)

    return {
        family: {
            "total": len(items),
            "passed": sum(item.passed for item in items),
            "pass_rate": round(sum(item.passed for item in items) / len(items), 4),
        }
        for family, items in sorted(families.items())
    }


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
        llm_fallback_provider=arguments.fallback_provider,
    )
    llm_client = create_llm_client(settings)
    extractor = SubmissionExtractor(llm_client)
    system_name = getattr(llm_client, "name", llm_client.provider)

    golden_cases = load_golden_cases(arguments.dataset)

    if arguments.case_id or arguments.case_prefix:
        golden_cases = [
            case
            for case in golden_cases
            if case.case_id in arguments.case_id
            or any(case.case_id.startswith(prefix) for prefix in arguments.case_prefix)
        ]

    if not golden_cases:
        parser.error("No golden cases match the provided selection.")

    case_reports: list[dict[str, object]] = []
    evaluations: list[CaseEvaluation] = []
    errored_cases = 0

    for index, golden_case in enumerate(golden_cases):
        if index and arguments.delay_seconds:
            time.sleep(arguments.delay_seconds)

        try:
            evaluation, case_report = evaluate_case(
                extractor=extractor,
                golden_case=golden_case,
            )
        except LLMClientError as error:
            errored_cases += 1
            evaluation = CaseEvaluation(
                case_id=golden_case.case_id,
                passed=False,
                checks={"provider_call": False},
                failures=[f"provider_error: {error}"],
            )
            case_report = {
                "case_id": golden_case.case_id,
                "duration_ms": None,
                "evaluation": evaluation.model_dump(mode="json"),
                "result": None,
            }

        evaluations.append(evaluation)
        case_reports.append(case_report)

        status = "PASS" if evaluation.passed else "FAIL"

        print(f"[{status}] {golden_case.case_id} ({case_report['duration_ms']} ms)")

        for failure in evaluation.failures:
            print(f"  - {failure}")

    passed_cases = sum(case_report["evaluation"]["passed"] for case_report in case_reports)
    total_cases = len(case_reports)

    report = {
        "provider": system_name,
        "model": llm_client.model,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "dataset": str(arguments.dataset),
        "summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": total_cases - passed_cases,
            "pass_rate": round(passed_cases / total_cases, 4),
            "errored_cases": errored_cases,
            "by_family": summarize_by_family(evaluations),
        },
        "field_metrics": compute_field_metrics(evaluations),
        "cases": case_reports,
    }

    arguments.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    output_path = arguments.output_directory / (f"{system_name}_{timestamp}.json")

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
    metrics = report["field_metrics"]
    print(f"Errored cases (provider): {errored_cases}")
    print(f"Missing-field recall: {metrics['missing_field_recall']}")
    print(f"Hallucination rate: {metrics['hallucination']['rate']}")
    print("Per-field accuracy:")
    for field_name, values in metrics["fields"].items():
        print(f"  {field_name}: {values['correct']}/{values['total']} ({values['accuracy']:.1%})")
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
