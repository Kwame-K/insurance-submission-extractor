"""Create extraction and evaluation history tables.

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submission_id", sa.String(255), nullable=False),
        sa.Column("correlation_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=True),
        sa.Column("missing_field_count", sa.Integer(), nullable=True),
        sa.Column("unsupported_fields", JSON_TYPE, nullable=False),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("llm_calls", sa.Integer(), nullable=True),
        sa.Column("failed_llm_calls", sa.Integer(), nullable=True),
        sa.Column("attempts", JSON_TYPE, nullable=False),
    )
    op.create_index("ix_extraction_runs_recorded_at", "extraction_runs", ["recorded_at"])
    op.create_index("ix_extraction_runs_submission_id", "extraction_runs", ["submission_id"])
    op.create_index("ix_extraction_runs_correlation_id", "extraction_runs", ["correlation_id"])
    op.create_index("ix_extraction_runs_provider", "extraction_runs", ["provider"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("system", sa.String(128), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("dataset", sa.String(512), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("failed_cases", sa.Integer(), nullable=False),
        sa.Column("errored_cases", sa.Integer(), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=False),
        sa.Column("missing_field_recall", sa.Float(), nullable=True),
        sa.Column("hallucination_rate", sa.Float(), nullable=True),
        sa.Column("by_family", JSON_TYPE, nullable=False),
        sa.Column("field_metrics", JSON_TYPE, nullable=False),
    )
    op.create_index("ix_evaluation_runs_evaluated_at", "evaluation_runs", ["evaluated_at"])
    op.create_index("ix_evaluation_runs_system", "evaluation_runs", ["system"])

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_id", sa.String(255), nullable=False),
        sa.Column("family", sa.String(128), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("failures", JSON_TYPE, nullable=False),
        sa.Column("checks", JSON_TYPE, nullable=False),
        sa.Column("hallucinated_fields", JSON_TYPE, nullable=False),
    )
    op.create_index("ix_evaluation_cases_run_id", "evaluation_cases", ["run_id"])
    op.create_index("ix_evaluation_cases_case_id", "evaluation_cases", ["case_id"])
    op.create_index("ix_evaluation_cases_family", "evaluation_cases", ["family"])


def downgrade() -> None:
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_runs")
    op.drop_table("extraction_runs")
