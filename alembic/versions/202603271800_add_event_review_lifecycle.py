"""add event review lifecycle fields

Revision ID: 202603271800
Revises: 202512131400_add_source_to_dedup_keys
Create Date: 2026-03-27 18:00:00.000000

Adds review_status, reviewed_by, reviewed_at, version, origin columns
to the events table and creates event_audit_log and event_versions tables.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202603271800"
down_revision = "202512131400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add review lifecycle columns to events table
    op.add_column(
        "events", sa.Column("version", sa.Integer(), nullable=True, server_default="1")
    )
    op.add_column(
        "events",
        sa.Column(
            "origin",
            sa.String(length=20),
            nullable=True,
            server_default="ai_extraction",
        ),
    )
    op.add_column(
        "events",
        sa.Column(
            "review_status",
            sa.String(length=20),
            nullable=True,
            server_default="needs_review",
        ),
    )
    op.add_column(
        "events", sa.Column("reviewed_by", sa.String(length=100), nullable=True)
    )
    op.add_column("events", sa.Column("reviewed_at", sa.DateTime(), nullable=True))

    # Backfill existing events
    op.execute("UPDATE events SET version = 1 WHERE version IS NULL")
    op.execute("UPDATE events SET origin = 'ai_extraction' WHERE origin IS NULL")
    op.execute(
        "UPDATE events SET review_status = 'needs_review' WHERE review_status IS NULL"
    )

    # Create event_audit_log table
    op.create_table(
        "event_audit_log",
        sa.Column("audit_id", sa.String(length=36), primary_key=True),
        sa.Column("event_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("changes", sa.Text(), nullable=True),  # JSON
        sa.Column(
            "actor", sa.String(length=100), nullable=False, server_default="pipeline"
        ),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )

    # Create event_versions table (full snapshots)
    op.create_table(
        "event_versions",
        sa.Column("version_id", sa.String(length=36), primary_key=True),
        sa.Column("event_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=20), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),  # JSON
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # Create index for review queue queries
    op.create_index("ix_events_review_status", "events", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_events_review_status", table_name="events")
    op.drop_table("event_versions")
    op.drop_table("event_audit_log")
    op.drop_column("events", "reviewed_at")
    op.drop_column("events", "reviewed_by")
    op.drop_column("events", "review_status")
    op.drop_column("events", "origin")
    op.drop_column("events", "version")
