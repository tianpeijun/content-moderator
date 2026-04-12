"""Initial tables for content moderation system.

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- rules ---
    op.create_table(
        "rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("business_type", sa.String(100), nullable=True),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- rule_versions ---
    op.create_table(
        "rule_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("modified_by", sa.String(100), nullable=True),
        sa.Column(
            "modified_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("change_summary", sa.Text(), nullable=True),
    )

    # --- model_config ---
    op.create_table(
        "model_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fallback_result", sa.String(20), nullable=True),
        sa.Column(
            "cost_per_1k_input", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "cost_per_1k_output", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- test_suites ---
    op.create_table(
        "test_suites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("file_key", sa.String(500), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- test_records ---
    op.create_table(
        "test_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "test_suite_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_suites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_ids", postgresql.JSONB(), nullable=True),
        sa.Column("model_config_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="'pending'"
        ),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    # --- moderation_logs ---
    op.create_table(
        "moderation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", sa.String(36), unique=True, nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="'pending'"
        ),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column("input_image_url", sa.String(1000), nullable=True),
        sa.Column("business_type", sa.String(100), nullable=True),
        sa.Column("final_prompt", sa.Text(), nullable=True),
        sa.Column("model_response", sa.Text(), nullable=True),
        sa.Column("result", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("matched_rules", postgresql.JSONB(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- indexes on moderation_logs ---
    op.create_index(
        "idx_logs_result_created",
        "moderation_logs",
        ["result", "created_at"],
    )
    op.create_index(
        "idx_logs_business_type_created",
        "moderation_logs",
        ["business_type", "created_at"],
    )
    op.create_index(
        "idx_logs_task_id",
        "moderation_logs",
        ["task_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_logs_task_id", table_name="moderation_logs")
    op.drop_index("idx_logs_business_type_created", table_name="moderation_logs")
    op.drop_index("idx_logs_result_created", table_name="moderation_logs")
    op.drop_table("moderation_logs")
    op.drop_table("test_records")
    op.drop_table("test_suites")
    op.drop_table("model_config")
    op.drop_table("rule_versions")
    op.drop_table("rules")
