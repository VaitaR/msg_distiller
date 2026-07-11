"""Add object_suggestions queue for unmatched object registry names.

When canonicalize_object fails during extraction, the raw name lands here
for later review; approving a suggestion writes a synonym back to the
object registry YAML.

Revision ID: 202607111400
Revises: 202607111300
"""

from alembic import op

revision = "202607111400"
down_revision = "202607111300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS object_suggestions (
            id SERIAL PRIMARY KEY,
            name_normalized TEXT NOT NULL UNIQUE,
            name_raw_sample TEXT NOT NULL,
            occurrences INTEGER NOT NULL DEFAULT 1,
            sample_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending',
            approved_object_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_object_suggestions_status"
        " ON object_suggestions(status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS object_suggestions")
