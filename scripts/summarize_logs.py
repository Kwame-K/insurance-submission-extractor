"""Summarize extraction logs: fallback, review and error rates, and latency."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from insurance_submission_extractor.services.telemetry import read_records, summarize_records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_path", type=Path, help="JSONL file written via EXTRACTION_LOG_PATH.")
    arguments = parser.parse_args()

    if not arguments.log_path.exists():
        parser.error(f"Log file not found: {arguments.log_path}")

    records = read_records(arguments.log_path)
    if not records:
        print("No extraction records found.", file=sys.stderr)
        raise SystemExit(1)

    print(json.dumps(summarize_records(records), indent=2))


if __name__ == "__main__":
    main()
