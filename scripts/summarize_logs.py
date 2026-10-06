"""Summarize extraction history: fallback, review and error rates, latency, tokens and cost.

Reads a JSONL log file, or a database when no file is given.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.persistence import DatabaseStore
from insurance_submission_extractor.services.telemetry import read_records, summarize_records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "log_path",
        type=Path,
        nargs="?",
        help="JSONL file written via EXTRACTION_LOG_PATH.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Read from this database instead of a file (defaults to DATABASE_URL).",
    )
    parser.add_argument(
        "--evaluations",
        action="store_true",
        help="List the stored evaluation runs instead of summarizing extractions.",
    )
    arguments = parser.parse_args()

    if arguments.log_path is not None and (arguments.evaluations or arguments.database_url):
        parser.error("A log path cannot be combined with --database-url or --evaluations.")

    if arguments.log_path is not None:
        if not arguments.log_path.exists():
            parser.error(f"Log file not found: {arguments.log_path}")
        records = read_records(arguments.log_path)
    else:
        database_url = arguments.database_url or Settings().database_url
        if not database_url:
            parser.error("Provide a log path, --database-url, or set DATABASE_URL.")

        store = DatabaseStore(database_url)
        if arguments.evaluations:
            print(json.dumps(store.evaluation_runs(), indent=2))
            return
        records = store.extraction_records()

    if not records:
        print("No extraction records found.", file=sys.stderr)
        raise SystemExit(1)

    print(json.dumps(summarize_records(records), indent=2))


if __name__ == "__main__":
    main()
