from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm import LLMClientError, create_llm_client
from insurance_submission_extractor.services import SubmissionExtractor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="insurance-submission-extractor",
        description=(
            "Extract structured commercial insurance submission data from unstructured text."
        ),
    )

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--input-file",
        type=Path,
        help="Path to a UTF-8 plain text submission file.",
    )
    source_group.add_argument(
        "--text",
        help="Submission text provided directly in the command line.",
    )

    parser.add_argument(
        "--submission-id",
        required=True,
        help="Unique identifier assigned to the submission.",
    )

    return parser


def load_submission_text(arguments: argparse.Namespace) -> str:
    if arguments.text:
        return arguments.text.strip()

    input_file: Path = arguments.input_file

    if not input_file.exists():
        raise ValueError(f"Input file does not exist: {input_file}")

    if not input_file.is_file():
        raise ValueError(f"Input path is not a file: {input_file}")

    submission_text = input_file.read_text(encoding="utf-8").strip()

    if not submission_text:
        raise ValueError(f"Input file is empty: {input_file}")

    return submission_text


def main() -> None:
    parser = build_parser()
    arguments = parser.parse_args()

    try:
        submission_text = load_submission_text(arguments)

        settings = Settings()
        llm_client = create_llm_client(settings)
        extractor = SubmissionExtractor(llm_client)

        result = extractor.extract(
            submission_text=submission_text,
            submission_id=arguments.submission_id,
        )

        print(
            json.dumps(
                result.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            )
        )
    except (LLMClientError, ValueError) as error:
        print(
            f"Error: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
