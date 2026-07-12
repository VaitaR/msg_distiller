"""Backfill cluster_key/dedup_key to include source_id.

P1.3 in docs/TECHNICAL_SPEC_EXTRACTION_QUALITY.md requires dedup keys to be
source-aware to avoid cross-source collisions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "202512131400"
down_revision = "202511060930"
branch_labels = None
depends_on = None


def _normalize_anchors(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item is not None]
    return []


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def upgrade() -> None:
    bind = op.get_bind()

    rows = bind.execute(
        sa.text(
            """
            SELECT event_id, source_id, action, object_id, object_name_raw, anchors,
                   status, actual_start, actual_end, planned_start, planned_end, environment
            FROM events
            """
        )
    ).mappings()

    updates: list[dict[str, Any]] = []
    for row in rows:
        source_id = (row.get("source_id") or "slack").strip()
        action = (row.get("action") or "").strip()
        object_key = (row.get("object_id") or "").strip() or (
            (row.get("object_name_raw") or "").lower().strip()
        )
        anchors = _normalize_anchors(row.get("anchors"))
        top_anchor = anchors[0] if anchors else ""

        cluster_material = f"{source_id}||{action}||{object_key}||{top_anchor}"
        cluster_key = hashlib.sha1(cluster_material.encode("utf-8")).hexdigest()

        status_val = (row.get("status") or "").strip()
        env_val = (row.get("environment") or "").strip()
        primary_time = (
            row.get("actual_start")
            or row.get("actual_end")
            or row.get("planned_start")
            or row.get("planned_end")
        )
        time_str = _iso(primary_time) or "no-time"

        dedup_material = f"{cluster_key}||{status_val}||{time_str}||{env_val}"
        dedup_key = hashlib.sha1(dedup_material.encode("utf-8")).hexdigest()

        updates.append(
            {
                "event_id": row["event_id"],
                "cluster_key": cluster_key,
                "dedup_key": dedup_key,
            }
        )

    if not updates:
        return

    bind.execute(
        sa.text(
            """
            UPDATE events
            SET cluster_key = :cluster_key,
                dedup_key = :dedup_key
            WHERE event_id = :event_id
            """
        ),
        updates,
    )


def downgrade() -> None:
    """Keys are not reversible; leave as-is."""
