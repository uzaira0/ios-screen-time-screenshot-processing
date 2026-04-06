"""Add workflow engine tables (workflow_execution, activity_execution, workflow_signal, workflow_audit_log)

Revision ID: l0m1n2o3p4q5
Revises: k9l0m1n2o3p4
Create Date: 2026-04-06 22:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "l0m1n2o3p4q5"
down_revision: str | None = "k9l0m1n2o3p4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- workflow_execution --
    op.create_table(
        "workflow_execution",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("screenshot_id", sa.Integer, nullable=False),
        sa.Column("workflow_type", sa.String(64), nullable=False, server_default="preprocessing"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("current_activity", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workflow_execution_screenshot_id", "workflow_execution", ["screenshot_id"])
    # Partial unique index: only one active (pending/running) workflow per screenshot+type
    op.execute(
        "CREATE UNIQUE INDEX uq_workflow_screenshot_type "
        "ON workflow_execution (screenshot_id, workflow_type) "
        "WHERE status IN ('pending', 'running')"
    )

    # -- activity_execution --
    op.create_table(
        "activity_execution",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("workflow_id", sa.Integer, sa.ForeignKey("workflow_execution.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("progress_pct", sa.Float, server_default="0.0"),
        sa.Column("is_blocking", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("result_json", sa.JSON, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_class", sa.String(20), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_activity_workflow", "activity_execution", ["workflow_id"])

    # -- workflow_signal --
    op.create_table(
        "workflow_signal",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("workflow_id", sa.Integer, sa.ForeignKey("workflow_execution.id", ondelete="CASCADE"), nullable=False),
        sa.Column("signal_name", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON, nullable=True),
        sa.Column("consumed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_signal_pending", "workflow_signal", ["workflow_id", "consumed"])

    # -- workflow_audit_log --
    op.create_table(
        "workflow_audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("workflow_id", sa.Integer, sa.ForeignKey("workflow_execution.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_name", sa.String(64), nullable=True),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("attempt", sa.Integer, nullable=True),
        sa.Column("progress_pct", sa.Float, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workflow_audit_workflow", "workflow_audit_log", ["workflow_id"])


def downgrade() -> None:
    op.drop_table("workflow_audit_log")
    op.drop_table("workflow_signal")
    op.drop_table("activity_execution")
    op.execute("DROP INDEX IF EXISTS uq_workflow_screenshot_type")
    op.drop_table("workflow_execution")
