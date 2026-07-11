"""Add event_embeddings table (pgvector).

Stores one embedding per event for semantic search and the cross-source
dedup second pass. Requires the pgvector extension (use a pgvector-enabled
PostgreSQL image, e.g. pgvector/pgvector:pg16).

No ANN index on purpose: exact scan is both more accurate and fast enough
below ~50k events. Add an HNSW index when the table outgrows that.

Revision ID: 202607111200
Revises: 202603271800
"""

from alembic import op

revision = "202607111200"
down_revision = "202603271800"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS event_embeddings (
            event_id TEXT PRIMARY KEY
                REFERENCES events(event_id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            embedding vector(1536) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index("idx_event_embeddings_model", "event_embeddings", ["model"])


def downgrade() -> None:
    op.drop_index("idx_event_embeddings_model", table_name="event_embeddings")
    op.drop_table("event_embeddings")
