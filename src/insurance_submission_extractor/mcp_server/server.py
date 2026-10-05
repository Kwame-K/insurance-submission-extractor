"""MCP server exposing commercial insurance submission extraction over stdio."""

from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from insurance_submission_extractor.config import Settings
from insurance_submission_extractor.llm import LLMClientError, create_llm_client
from insurance_submission_extractor.services import SubmissionExtractor
from insurance_submission_extractor.services.http_adapter import to_http_result

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

mcp = MCPServer("insurance-submission-extractor")

_extractor: SubmissionExtractor | None = None

_EXTRACTION_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def get_extractor() -> SubmissionExtractor:
    """Create and cache the configured extraction service."""
    global _extractor
    if _extractor is None:
        _extractor = SubmissionExtractor(create_llm_client(Settings()))
    return _extractor


@mcp.tool(annotations=_EXTRACTION_TOOL)
def extract_submission(
    source_id: str,
    content: str,
    language: str = "en",
    source_type: str = "FREE_TEXT",
    document_name: str | None = None,
) -> dict[str, Any]:
    """Extract candidate data from a commercial insurance submission.

    Returns structured candidate data, missing fields, quality flags and review
    signals. It does not accept, decline, price or bind insurance.
    """
    del language, source_type, document_name
    try:
        result = get_extractor().extract(
            submission_text=content,
            submission_id=source_id,
        )
    except LLMClientError as error:
        raise RuntimeError(f"LLM_PROVIDER_ERROR: {error}") from error
    return to_http_result(source_id, result).model_dump(mode="json")


def main() -> None:
    """Start the MCP server using the stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
