"""Add thread_ts columns for Slack thread ingestion.

Thread replies are now ingested alongside root messages; thread_ts links a
reply (message, candidate, or extracted event) back to its thread root.
NULL means the message is a thread root or not threaded.

Revision ID: 202607111300
Revises: 202607111200
"""

from alembic import op

revision = "202607111300"
down_revision = "202607111200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE raw_slack_messages ADD COLUMN IF NOT EXISTS thread_ts TEXT"
    )
    op.execute("ALTER TABLE event_candidates ADD COLUMN IF NOT EXISTS thread_ts TEXT")
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS thread_ts TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS thread_ts")
    op.execute("ALTER TABLE event_candidates DROP COLUMN IF EXISTS thread_ts")
    op.execute("ALTER TABLE raw_slack_messages DROP COLUMN IF EXISTS thread_ts")
