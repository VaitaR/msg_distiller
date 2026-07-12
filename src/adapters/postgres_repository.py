"""PostgreSQL repository implementation using psycopg2 with connection pooling."""

import json
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import sleep
from typing import TYPE_CHECKING, Any, Final, cast

import pytz
from psycopg2 import Error as PsycopgError
from psycopg2 import extensions
from psycopg2 import pool as psycopg2_pool
from psycopg2.extras import RealDictCursor, register_uuid

from src.adapters.bulk_persistence import (
    DatabaseBackend,
    EventDTO,
    RelationDTO,
    upsert_event_relations_bulk,
    upsert_events_bulk,
)
from src.adapters.postgres_task_queue import PostgresTaskQueue
from src.config.logging_config import get_logger
from src.domain.candidate_constants import CANDIDATE_LEASE_TIMEOUT
from src.domain.exceptions import RepositoryError
from src.domain.models import (
    CandidateStatus,
    Event,
    EventAuditEntry,
    EventCandidate,
    LLMCallMetadata,
    MessageSource,
    ReviewLifecycleStatus,
    SlackMessage,
    TelegramMessage,
)
from src.domain.protocols import MessageRecord
from src.ports.task_queue import TaskQueuePort

if TYPE_CHECKING:
    from src.adapters.query_builders import (
        CandidateQueryCriteria,
        EventQueryCriteria,
    )
    from src.config.settings import Settings


DEFAULT_STATE_TABLE: Final[str] = "slack_ingestion_state"
TELEGRAM_STATE_TABLE: Final[str] = "ingestion_state_telegram"
STATE_TABLE_FALLBACK_BY_SOURCE: Final[dict[MessageSource, str]] = {
    MessageSource.SLACK: DEFAULT_STATE_TABLE,
    MessageSource.TELEGRAM: TELEGRAM_STATE_TABLE,
}

DEFAULT_POOL_MIN_CONNECTIONS: Final[int] = 1
DEFAULT_POOL_MAX_CONNECTIONS: Final[int] = 10
POOL_ACQUIRE_MAX_ATTEMPTS_DEFAULT: Final[int] = 5
POOL_ACQUIRE_BASE_DELAY_SECONDS: Final[float] = 0.1
POOL_ACQUIRE_MAX_DELAY_SECONDS: Final[float] = 2.0
POOL_USAGE_WARNING_THRESHOLD: Final[float] = 0.8

logger = get_logger(__name__)

_UUID_ADAPTER_REGISTERED: bool = False
_UUID_ADAPTER_LOCK: Lock = Lock()


def _ensure_uuid_adapter_registered() -> None:
    """Register psycopg2 adapters required by the repository."""

    global _UUID_ADAPTER_REGISTERED
    if _UUID_ADAPTER_REGISTERED:
        return

    with _UUID_ADAPTER_LOCK:
        if _UUID_ADAPTER_REGISTERED:
            return
        register_uuid()
        _UUID_ADAPTER_REGISTERED = True


class PostgresRepository:
    """PostgreSQL repository backed by a connection pool."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        settings: "Settings | None" = None,
    ):
        """Initialize PostgreSQL repository with pooled connections."""
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._settings = settings
        self._bulk_chunk_size = settings.bulk_upsert_chunk_size if settings else 500
        if self._bulk_chunk_size <= 0:
            raise RepositoryError("bulk_upsert_chunk_size must be positive")

        self._statement_timeout_ms = (
            settings.postgres_statement_timeout_ms if settings else 10_000
        )
        self._connect_timeout_seconds = (
            settings.postgres_connect_timeout_seconds if settings else 10
        )
        self._application_name = (
            settings.postgres_application_name if settings else "slack_event_manager"
        )
        self._pool_min_connections = (
            settings.postgres_min_connections
            if settings
            else DEFAULT_POOL_MIN_CONNECTIONS
        )
        self._pool_max_connections = (
            settings.postgres_max_connections
            if settings
            else DEFAULT_POOL_MAX_CONNECTIONS
        )
        self._ssl_mode = settings.postgres_ssl_mode if settings else None

        self._pool_acquire_max_attempts = POOL_ACQUIRE_MAX_ATTEMPTS_DEFAULT
        self._pool_acquire_base_delay_seconds = POOL_ACQUIRE_BASE_DELAY_SECONDS
        self._pool_acquire_max_delay_seconds = POOL_ACQUIRE_MAX_DELAY_SECONDS
        self._pool_usage_warning_threshold = POOL_USAGE_WARNING_THRESHOLD
        self._pool_in_use_count = 0
        self._pool_high_watermark = 0
        self._pool_usage_warning_emitted = False
        self._pool_lock = Lock()
        self._task_queue_adapter: PostgresTaskQueue | None = None

        if self._pool_min_connections <= 0:
            raise RepositoryError("postgres_min_connections must be positive")
        if self._pool_max_connections < self._pool_min_connections:
            raise RepositoryError(
                "postgres_max_connections must be greater than or equal to postgres_min_connections"
            )

        _ensure_uuid_adapter_registered()
        self._pool = self._create_pool()

    def _create_pool(self) -> psycopg2_pool.ThreadedConnectionPool:
        """Create a PostgreSQL connection pool with validation."""
        options_parts: list[str] = [
            f"-c statement_timeout={self._statement_timeout_ms}",
            f"-c application_name={self._application_name}",
        ]
        options = " ".join(options_parts)

        conn_kwargs: dict[str, Any] = {
            "host": self._host,
            "port": self._port,
            "database": self._database,
            "user": self._user,
            "password": self._password,
            "connect_timeout": self._connect_timeout_seconds,
            "options": options,
        }
        if self._ssl_mode:
            conn_kwargs["sslmode"] = self._ssl_mode

        try:
            pool = psycopg2_pool.ThreadedConnectionPool(
                self._pool_min_connections,
                self._pool_max_connections,
                **conn_kwargs,
            )
        except PsycopgError as exc:
            raise RepositoryError(
                f"Failed to initialize PostgreSQL pool: {exc}"
            ) from exc

        try:
            conn = pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            finally:
                pool.putconn(conn)
        except PsycopgError as exc:
            pool.closeall()
            raise RepositoryError(f"PostgreSQL validation query failed: {exc}") from exc

        logger.info(
            "postgres_pool_initialized",
            host=self._host,
            port=self._port,
            database=self._database,
            min_connections=self._pool_min_connections,
            max_connections=self._pool_max_connections,
            statement_timeout_ms=self._statement_timeout_ms,
        )
        return pool

    def _acquire_connection_with_retry(self) -> extensions.connection:
        """Acquire a connection from the pool with exponential backoff."""
        attempt = 0
        delay = self._pool_acquire_base_delay_seconds
        while True:
            attempt += 1
            try:
                conn = self._pool.getconn()
            except psycopg2_pool.PoolError as exc:
                if attempt >= self._pool_acquire_max_attempts:
                    logger.error(
                        "postgres_pool_acquire_failed",
                        attempts=attempt,
                        max_attempts=self._pool_acquire_max_attempts,
                        max_connections=self._pool_max_connections,
                        in_use=self._pool_in_use_count,
                    )
                    raise RepositoryError(
                        "Failed to acquire PostgreSQL connection from pool"
                    ) from exc

                logger.warning(
                    "postgres_pool_exhausted_retry",
                    attempt=attempt,
                    wait_seconds=delay,
                    max_attempts=self._pool_acquire_max_attempts,
                    max_connections=self._pool_max_connections,
                    in_use=self._pool_in_use_count,
                )
                sleep(delay)
                delay = min(delay * 2, self._pool_acquire_max_delay_seconds)
                continue

            self._register_connection_checkout()
            return conn

    def _register_connection_checkout(self) -> None:
        """Update pool usage counters after a checkout."""
        with self._pool_lock:
            self._pool_in_use_count += 1
            if self._pool_in_use_count > self._pool_high_watermark:
                self._pool_high_watermark = self._pool_in_use_count
                logger.info(
                    "postgres_pool_high_watermark",
                    high_watermark=self._pool_high_watermark,
                    max_connections=self._pool_max_connections,
                )

            usage_ratio = self._pool_in_use_count / self._pool_max_connections
            if (
                usage_ratio >= self._pool_usage_warning_threshold
                and not self._pool_usage_warning_emitted
            ):
                self._pool_usage_warning_emitted = True
                logger.warning(
                    "postgres_pool_usage_high",
                    in_use=self._pool_in_use_count,
                    max_connections=self._pool_max_connections,
                    threshold=self._pool_usage_warning_threshold,
                )

    def _register_connection_checkin(self) -> None:
        """Update pool usage counters after a checkin."""
        with self._pool_lock:
            if self._pool_in_use_count > 0:
                self._pool_in_use_count -= 1

            usage_ratio = self._pool_in_use_count / self._pool_max_connections
            if usage_ratio < self._pool_usage_warning_threshold:
                self._pool_usage_warning_emitted = False

    def _release_connection(
        self,
        conn: extensions.connection,
        *,
        close: bool,
        reason: str | None,
    ) -> None:
        """Return a connection to the pool and update usage metrics."""
        try:
            self._pool.putconn(conn, close=close)
        except PsycopgError:
            logger.warning(
                "postgres_putconn_failed",
                database=self._database,
                close=close,
                reason=reason,
                exc_info=True,
            )
        finally:
            self._register_connection_checkin()
            if close and reason:
                logger.warning(
                    "postgres_connection_closed",
                    reason=reason,
                    max_connections=self._pool_max_connections,
                    in_use=self._pool_in_use_count,
                )

    def close(self) -> None:
        """Close all connections in the pool."""
        self._pool.closeall()
        with self._pool_lock:
            self._pool_in_use_count = 0
            self._pool_usage_warning_emitted = False
        logger.info(
            "postgres_pool_closed",
            database=self._database,
            high_watermark=self._pool_high_watermark,
        )

    def task_queue(self) -> TaskQueuePort:
        """Provide task queue adapter tied to this repository."""

        if self._task_queue_adapter is None:

            def _provider() -> AbstractContextManager[Any]:
                return self._get_connection()

            self._task_queue_adapter = PostgresTaskQueue(_provider)
        return self._task_queue_adapter

    def _get_state_table_name(self, source_id: MessageSource | None) -> str:
        """Get state table name for the given source."""
        if source_id is None:
            return DEFAULT_STATE_TABLE

        if self._settings:
            source_config = self._settings.get_source_config(source_id)
            if source_config and source_config.state_table:
                return source_config.state_table

        return STATE_TABLE_FALLBACK_BY_SOURCE.get(source_id, DEFAULT_STATE_TABLE)

    @contextmanager
    def _get_connection(self) -> Iterator[extensions.connection]:
        """Borrow a connection from the pool and ensure cleanup."""
        conn: extensions.connection | None = None
        try:
            conn = self._acquire_connection_with_retry()
            conn.autocommit = False
            yield conn
        except PsycopgError as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except PsycopgError:
                    logger.warning(
                        "postgres_connection_rollback_failed",
                        database=self._database,
                        exc_info=True,
                    )
                finally:
                    self._release_connection(conn, close=True, reason="rollback_error")
                    conn = None
            raise RepositoryError(f"PostgreSQL connection error: {exc}") from exc
        finally:
            if conn is not None:
                try:
                    status = conn.get_transaction_status()
                    if status in (
                        extensions.TRANSACTION_STATUS_INTRANS,
                        extensions.TRANSACTION_STATUS_INERROR,
                    ):
                        conn.rollback()
                except PsycopgError:
                    logger.warning(
                        "postgres_connection_cleanup_failed",
                        database=self._database,
                        exc_info=True,
                    )
                    self._release_connection(conn, close=True, reason="cleanup_error")
                else:
                    self._release_connection(conn, close=False, reason=None)

    def _row_to_message(self, row: dict[str, Any]) -> SlackMessage:
        """Convert database row to SlackMessage.

        Args:
            row: Database row as dict

        Returns:
            SlackMessage instance
        """
        return SlackMessage(
            message_id=row["message_id"],
            channel=row["channel_id"],
            user=row["user"],
            user_real_name=row.get("user_real_name"),
            user_display_name=row.get("user_display_name"),
            user_email=row.get("user_email"),
            user_profile_image=row.get("user_profile_image"),
            ts=row["ts"],
            ts_dt=row["ts_dt"],
            text=row["text_raw"],
            blocks_text=row.get("blocks_text", ""),
            text_norm=row["text_norm"],
            is_bot=row["is_bot"],
            subtype=row.get("subtype"),
            reply_count=row["reply_count"],
            thread_ts=row.get("thread_ts"),
            reactions=row.get("reactions") or {},  # Already parsed dict from JSONB
            links_raw=row.get("links_raw") or [],  # Already parsed list from JSONB
            links_norm=row.get("links_norm") or [],  # Already parsed list from JSONB
            anchors=row.get("anchors") or [],  # Already parsed list from JSONB
            attachments_count=row.get("attachments_count", 0),
            files_count=row.get("files_count", 0),
            total_reactions=row.get("total_reactions", 0),
            permalink=row.get("permalink"),
            edited_ts=row.get("edited_ts"),
            edited_user=row.get("edited_user"),
        )

    def _row_to_candidate(self, row: dict[str, Any]) -> EventCandidate:
        """Convert database row to EventCandidate.

        Args:
            row: Database row as dict

        Returns:
            EventCandidate instance
        """
        from src.domain.models import CandidateStatus, ScoringFeatures

        source_raw = row.get("source_id") or MessageSource.SLACK.value
        source_id = MessageSource(source_raw) if source_raw else MessageSource.SLACK

        return EventCandidate(
            message_id=row["message_id"],
            channel=row["channel"],
            ts_dt=row["ts_dt"],  # Already datetime from PostgreSQL
            text_norm=row["text_norm"] or "",
            links_norm=row.get("links_norm") or [],
            anchors=row.get("anchors") or [],
            score=row["score"] or 0.0,
            status=CandidateStatus(row["status"])
            if row["status"]
            else CandidateStatus.NEW,
            features=ScoringFeatures.model_validate(row["features_json"] or {}),
            source_id=source_id,
            thread_ts=row.get("thread_ts"),
            lease_attempts=int(row.get("lease_attempts") or 0),
            processing_started_at=row.get("processing_started_at"),
        )

    def _row_to_event(self, row: dict[str, Any]) -> Event:
        """Convert database row to Event with new comprehensive structure.

        Args:
            row: Database row as dict

        Returns:
            Event instance
        """
        from uuid import UUID

        from src.domain.models import (
            ActionType,
            ChangeType,
            Environment,
            EventCategory,
            EventStatus,
            MessageSource,
            Severity,
            TimeSource,
        )

        source_id_value = row.get("source_id") or MessageSource.SLACK.value
        extracted_at_raw = row.get("extracted_at")
        if not isinstance(extracted_at_raw, datetime):
            raise RepositoryError("Event row missing extracted_at timestamp")
        if extracted_at_raw.tzinfo is None:
            extracted_at = extracted_at_raw.replace(tzinfo=pytz.UTC)
        else:
            extracted_at = extracted_at_raw.astimezone(pytz.UTC)

        message_published_at_raw = row.get("message_published_at")
        if isinstance(message_published_at_raw, datetime):
            if message_published_at_raw.tzinfo is None:
                message_published_at = message_published_at_raw.replace(tzinfo=pytz.UTC)
            else:
                message_published_at = message_published_at_raw.astimezone(pytz.UTC)
        else:
            message_published_at = None

        return Event(
            # Identification
            event_id=UUID(row["event_id"]),
            message_id=row["message_id"],
            source_channels=row.get("source_channels")
            or [],  # Already parsed from JSONB
            extracted_at=extracted_at,
            message_published_at=message_published_at,
            thread_ts=row.get("thread_ts"),
            source_id=MessageSource(source_id_value),
            # Title slots
            action=ActionType(row["action"]),
            object_id=row.get("object_id"),
            object_name_raw=row["object_name_raw"],
            qualifiers=row.get("qualifiers") or [],  # Already parsed from JSONB
            stroke=row.get("stroke"),
            anchor=row.get("anchor"),
            # Classification
            category=EventCategory(row["category"]),
            status=EventStatus(row["status"]),
            change_type=ChangeType(row["change_type"]),
            environment=Environment(row["environment"]),
            severity=Severity(row["severity"]) if row.get("severity") else None,
            # Time fields
            planned_start=row.get("planned_start"),  # Already datetime or None
            planned_end=row.get("planned_end"),
            actual_start=row.get("actual_start"),
            actual_end=row.get("actual_end"),
            time_source=TimeSource(row["time_source"]),
            time_confidence=row.get("time_confidence", 0.0),
            # Content
            summary=row.get("summary") or "",
            why_it_matters=row.get("why_it_matters"),
            impact_area=row.get("impact_area") or [],  # Already parsed from JSONB
            impact_type=row.get("impact_type") or [],  # Already parsed from JSONB
            links=row.get("links") or [],  # Already parsed from JSONB
            anchors=row.get("anchors") or [],  # Already parsed from JSONB
            # Metadata
            confidence=row.get("confidence", 0.0),
            importance=row.get("importance", 0),
            cluster_key=row.get("cluster_key") or "",
            dedup_key=row.get("dedup_key") or "",
        )

    def save_messages(self, messages: list[SlackMessage]) -> int:
        """Save messages to PostgreSQL (upsert).

        Args:
            messages: List of slack messages

        Returns:
            Number of messages saved

        Raises:
            RepositoryError: On storage errors
        """
        if not messages:
            return 0

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for msg in messages:
                    cur.execute(
                        """
                        INSERT INTO raw_slack_messages (
                            message_id, channel_id, "user", user_real_name,
                            user_display_name, user_email, user_profile_image,
                            ts, ts_dt, text_raw, blocks_text, text_norm, is_bot, subtype,
                            reply_count, thread_ts, reactions, links_raw, links_norm, anchors,
                            attachments_count, files_count, total_reactions,
                            permalink, edited_ts, edited_user
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (message_id) DO UPDATE SET
                            user_real_name = EXCLUDED.user_real_name,
                            user_display_name = EXCLUDED.user_display_name,
                            user_email = EXCLUDED.user_email,
                            user_profile_image = EXCLUDED.user_profile_image,
                            text_raw = EXCLUDED.text_raw,
                            blocks_text = EXCLUDED.blocks_text,
                            text_norm = EXCLUDED.text_norm,
                            reply_count = EXCLUDED.reply_count,
                            thread_ts = EXCLUDED.thread_ts,
                            reactions = EXCLUDED.reactions,
                            links_raw = EXCLUDED.links_raw,
                            links_norm = EXCLUDED.links_norm,
                            anchors = EXCLUDED.anchors,
                            attachments_count = EXCLUDED.attachments_count,
                            files_count = EXCLUDED.files_count,
                            total_reactions = EXCLUDED.total_reactions,
                            permalink = EXCLUDED.permalink,
                            edited_ts = EXCLUDED.edited_ts,
                            edited_user = EXCLUDED.edited_user
                        """,
                        (
                            msg.message_id,
                            msg.channel,
                            msg.user,
                            msg.user_real_name,
                            msg.user_display_name,
                            msg.user_email,
                            msg.user_profile_image,
                            msg.ts,
                            msg.ts_dt,
                            msg.text,
                            msg.blocks_text,
                            msg.text_norm,
                            msg.is_bot,
                            msg.subtype,
                            msg.reply_count,
                            msg.thread_ts,
                            json.dumps(msg.reactions),  # Convert dict to JSON
                            json.dumps(msg.links_raw),  # Convert list to JSON
                            json.dumps(msg.links_norm),  # Convert list to JSON
                            json.dumps(msg.anchors),  # Convert list to JSON
                            msg.attachments_count,
                            msg.files_count,
                            msg.total_reactions,
                            msg.permalink,
                            msg.edited_ts,
                            msg.edited_user,
                        ),
                    )
                conn.commit()
        return len(messages)

    def get_watermark(self, channel: str) -> str | None:
        """Get watermark timestamp for channel.

        Args:
            channel: Channel ID

        Returns:
            Last committed timestamp or None

        Raises:
            RepositoryError: On storage errors
        """
        row: dict[str, Any] | None = None
        with self._get_connection() as conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        "SELECT ts FROM channel_watermarks WHERE channel_id = %s",
                        (channel,),
                    )
                    row = cur.fetchone()
                conn.commit()
            except PsycopgError as exc:
                conn.rollback()
                raise RepositoryError(
                    f"Failed to fetch watermark for channel {channel}: {exc}"
                ) from exc
        return row["ts"] if row else None

    def update_watermark(self, channel: str, ts: str) -> None:
        """Update watermark for channel.

        Args:
            channel: Channel ID
            ts: New watermark timestamp

        Raises:
            RepositoryError: On storage errors
        """
        with self._get_connection() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO channel_watermarks (channel_id, ts, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (channel_id) DO UPDATE SET
                            ts = EXCLUDED.ts,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (channel, ts),
                    )
                conn.commit()
            except PsycopgError as exc:
                conn.rollback()
                raise RepositoryError(
                    f"Failed to update watermark for channel {channel}: {exc}"
                ) from exc

    def get_new_messages_for_candidates(self) -> list[SlackMessage]:
        """Get messages not yet in candidates table.

        Returns:
            List of messages to process

        Raises:
            RepositoryError: On storage errors
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=extensions.cursor) as cur:
                cur.execute(
                    """
                    SELECT m.*
                    FROM raw_slack_messages m
                    LEFT JOIN event_candidates c ON m.message_id = c.message_id
                    WHERE c.message_id IS NULL
                    ORDER BY m.ts_dt DESC
                    """
                )
                rows = cur.fetchall()
                # Get column names from cursor description
                columns = [desc[0] for desc in cur.description]
                return [
                    self._row_to_message(dict(zip(columns, row, strict=False)))
                    for row in rows
                ]

    def get_new_messages_for_candidates_by_source(
        self, source_id: MessageSource
    ) -> list[MessageRecord]:
        """Get messages not yet in candidates table for a specific source.

        This method is source-agnostic and returns messages that implement
        the MessageRecord protocol, allowing scoring logic to work with any source.

        Args:
            source_id: Message source (SLACK, TELEGRAM, etc.)

        Returns:
            List of messages implementing MessageRecord protocol

        Raises:
            RepositoryError: On storage errors
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=extensions.cursor) as cur:
                if source_id == MessageSource.SLACK:
                    # Query Slack messages
                    cur.execute(
                        """
                        SELECT m.*
                        FROM raw_slack_messages m
                        LEFT JOIN event_candidates c ON m.message_id = c.message_id
                        WHERE c.message_id IS NULL
                        ORDER BY m.ts_dt DESC
                        """
                    )
                    rows = cur.fetchall()
                    columns = [desc[0] for desc in cur.description]
                    return [
                        self._row_to_message(dict(zip(columns, row, strict=False)))
                        for row in rows
                    ]

                elif source_id == MessageSource.TELEGRAM:
                    # Query Telegram messages
                    cur.execute(
                        """
                        SELECT m.*
                        FROM raw_telegram_messages m
                        LEFT JOIN event_candidates c ON m.message_id = c.message_id
                        WHERE c.message_id IS NULL
                        ORDER BY m.message_date DESC
                        """
                    )
                    rows = cur.fetchall()
                    columns = [desc[0] for desc in cur.description]
                    from typing import cast

                    return cast(
                        "list[MessageRecord]",
                        [
                            self._row_to_telegram_message(
                                dict(zip(columns, row, strict=False))
                            )
                            for row in rows
                        ],
                    )

                else:
                    raise RepositoryError(
                        f"Unsupported message source: {source_id}. "
                        f"Supported sources: {[s.value for s in MessageSource]}"
                    )

    def save_candidates(self, candidates: list[EventCandidate]) -> int:
        """Save event candidates (upsert).

        Args:
            candidates: List of candidates

        Returns:
            Number of candidates saved

        Raises:
            RepositoryError: On storage errors
        """
        if not candidates:
            return 0

        with self._get_connection() as conn, conn.cursor() as cur:
            for cand in candidates:
                cur.execute(
                    """
                        INSERT INTO event_candidates (
                            message_id, channel, ts_dt, text_norm, links_norm,
                            anchors, score, status, features_json, source_id,
                            thread_ts, processing_started_at, lease_attempts
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (message_id) DO UPDATE SET
                            text_norm = EXCLUDED.text_norm,
                            links_norm = EXCLUDED.links_norm,
                            anchors = EXCLUDED.anchors,
                            score = EXCLUDED.score,
                            features_json = EXCLUDED.features_json,
                            status = EXCLUDED.status,
                            source_id = EXCLUDED.source_id,
                            thread_ts = EXCLUDED.thread_ts,
                            processing_started_at = EXCLUDED.processing_started_at,
                            lease_attempts = EXCLUDED.lease_attempts
                        """,
                    (
                        cand.message_id,
                        cand.channel,
                        cand.ts_dt,
                        cand.text_norm,
                        json.dumps(cand.links_norm),
                        json.dumps(cand.anchors),
                        cand.score,
                        cand.status.value,
                        json.dumps(cand.features.model_dump()),
                        cand.source_id.value,
                        cand.thread_ts,
                        cand.processing_started_at,
                        cand.lease_attempts,
                    ),
                )
            conn.commit()
        return len(candidates)

    def get_candidates_for_extraction(
        self,
        batch_size: int | None = 50,
        min_score: float | None = None,
        source_id: MessageSource | None = None,
    ) -> list[EventCandidate]:
        """Get candidates ready for LLM extraction.

        Args:
            batch_size: Maximum candidates to return (None = all)
            min_score: Minimum score filter
            source_id: Filter by message source (None = all sources)

        Returns:
            List of candidates ordered by score DESC

        Raises:
            RepositoryError: On storage errors
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                now = datetime.now(tz=pytz.UTC)
                stale_before = now - CANDIDATE_LEASE_TIMEOUT

                cur.execute(
                    """
                    UPDATE event_candidates
                    SET status = %s, processing_started_at = NULL
                    WHERE status = %s AND (
                        processing_started_at IS NULL OR processing_started_at < %s
                    )
                    """,
                    (
                        CandidateStatus.NEW.value,
                        CandidateStatus.PROCESSING.value,
                        stale_before,
                    ),
                )

                clauses = ["SELECT * FROM event_candidates WHERE status = 'new'"]
                params: list[Any] = []

                if source_id is not None:
                    clauses.append("AND source_id = %s")
                    params.append(source_id.value)

                if min_score is not None:
                    clauses.append("AND score >= %s")
                    params.append(min_score)

                clauses.append("ORDER BY score DESC")

                if batch_size is not None:
                    clauses.append("LIMIT %s")
                    params.append(batch_size)

                clauses.append("FOR UPDATE SKIP LOCKED")

                query = " ".join(clauses)
                cur.execute(query, params)
                rows = cur.fetchall()

                if not rows:
                    conn.commit()
                    return []

                message_ids = [row["message_id"] for row in rows]
                cur.execute(
                    """
                    UPDATE event_candidates
                    SET status = %s,
                        processing_started_at = %s,
                        lease_attempts = COALESCE(lease_attempts, 0) + 1
                    WHERE message_id = ANY(%s)
                    """,
                    (CandidateStatus.PROCESSING.value, now, message_ids),
                )

                conn.commit()

                return [
                    self._row_to_candidate(dict(row)).model_copy(
                        update={
                            "status": CandidateStatus.PROCESSING,
                            "processing_started_at": now,
                            "lease_attempts": (row.get("lease_attempts") or 0) + 1,
                        }
                    )
                    for row in rows
                ]

    def get_candidate_by_message_id(self, message_id: str) -> EventCandidate | None:
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM event_candidates
                    WHERE message_id = %s
                    """,
                    (message_id,),
                )
                row = cur.fetchone()

        if row is None:
            return None

        return self._row_to_candidate(dict(row))

    def get_message_metadata(
        self, message_id: str, source_id: MessageSource
    ) -> dict[str, Any]:
        """Return a small metadata subset for a raw message."""

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if source_id == MessageSource.SLACK:
                    cur.execute(
                        """
                        SELECT permalink, reply_count, total_reactions, attachments_count, files_count
                        FROM raw_slack_messages
                        WHERE message_id = %s
                        """,
                        (message_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return {}
                    attachments_count = int(row.get("attachments_count") or 0)
                    files_count = int(row.get("files_count") or 0)
                    return {
                        "permalink": row.get("permalink"),
                        "reply_count": int(row.get("reply_count") or 0),
                        "reactions_count": int(row.get("total_reactions") or 0),
                        "has_file": (attachments_count + files_count) > 0,
                        "file_mime": None,
                        "post_url": None,
                        "forwarded_from": None,
                    }

                if source_id == MessageSource.TELEGRAM:
                    cur.execute(
                        """
                        SELECT post_url, forward_from_channel, reply_count, reactions_count, has_file, file_mime
                        FROM raw_telegram_messages
                        WHERE message_id = %s
                        """,
                        (message_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return {}
                    return {
                        "post_url": row.get("post_url"),
                        "forwarded_from": row.get("forward_from_channel"),
                        "reply_count": int(row.get("reply_count") or 0),
                        "reactions_count": int(row.get("reactions_count") or 0),
                        "has_file": bool(row.get("has_file")),
                        "file_mime": row.get("file_mime"),
                        "permalink": None,
                    }

        return {}

    def get_recent_slack_messages(self, limit: int = 100) -> list[SlackMessage]:
        """Get most recent Slack messages for presentation use."""

        if limit <= 0:
            return []

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM raw_slack_messages
                    ORDER BY ts_dt DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                return [self._row_to_message(dict(row)) for row in rows]

    def get_recent_candidates(self, limit: int = 100) -> list[EventCandidate]:
        """Get most recent event candidates for presentation use."""

        if limit <= 0:
            return []

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM event_candidates
                    ORDER BY score DESC, ts_dt DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                return [self._row_to_candidate(dict(row)) for row in rows]

    def get_recent_events(self, limit: int = 100) -> list[Event]:
        """Get most recently extracted events for presentation use."""

        if limit <= 0:
            return []

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM events
                    ORDER BY extracted_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                return [self._row_to_event(dict(row)) for row in rows]

    def update_candidate_status(self, message_id: str, status: str) -> None:
        """Update candidate processing status.

        Args:
            message_id: Message ID
            status: New status (llm_ok, llm_fail)

        Raises:
            RepositoryError: On storage errors
        """
        with self._get_connection() as conn, conn.cursor() as cur:
            if status == CandidateStatus.PROCESSING.value:
                cur.execute(
                    """
                        UPDATE event_candidates
                        SET status = %s,
                            processing_started_at = %s,
                            lease_attempts = COALESCE(lease_attempts, 0) + 1
                        WHERE message_id = %s
                        """,
                    (status, datetime.now(tz=pytz.UTC), message_id),
                )
            else:
                cur.execute(
                    """
                        UPDATE event_candidates
                        SET status = %s, processing_started_at = NULL
                        WHERE message_id = %s
                        """,
                    (status, message_id),
                )
            conn.commit()

    def save_events(self, events: list[Event]) -> int:
        """Save events with versioning (upsert by dedup_key)."""

        if not events:
            return 0

        try:
            with self._get_connection() as conn:
                dtos = [
                    EventDTO.from_event(
                        event,
                        backend=DatabaseBackend.POSTGRES,
                        connection=conn,
                    )
                    for event in events
                ]
                upsert_events_bulk(dtos, chunk=self._bulk_chunk_size)

                relation_dtos: list[RelationDTO] = []
                for event in events:
                    if not event.relations:
                        continue
                    for relation in event.relations:
                        relation_dtos.append(
                            RelationDTO.from_relation(
                                str(event.event_id),
                                relation,
                                backend=DatabaseBackend.POSTGRES,
                                connection=conn,
                            )
                        )

                if relation_dtos:
                    upsert_event_relations_bulk(
                        relation_dtos, chunk=self._bulk_chunk_size
                    )

                return len(events)
        except PsycopgError as exc:  # pragma: no cover - defensive logging
            raise RepositoryError(f"Failed to save events: {exc}") from exc

    def get_events_in_window(self, start_dt: datetime, end_dt: datetime) -> list[Event]:
        """Get events within date window.

        Args:
            start_dt: Start datetime (UTC)
            end_dt: End datetime (UTC)

        Returns:
            List of events

        Raises:
            RepositoryError: On storage errors
        """
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=extensions.cursor) as cur:
                cur.execute(
                    """
                    SELECT * FROM events
                    WHERE COALESCE(actual_start, actual_end, planned_start, planned_end, message_published_at, extracted_at) >= %s
                      AND COALESCE(actual_start, actual_end, planned_start, planned_end, message_published_at, extracted_at) <= %s
                    ORDER BY COALESCE(actual_start, actual_end, planned_start, planned_end, message_published_at, extracted_at) DESC
                    """,
                    (start_dt, end_dt),
                )
                rows = cur.fetchall()
                # Get column names from cursor description
                columns = [desc[0] for desc in cur.description]
                return [
                    self._row_to_event(dict(zip(columns, row, strict=False)))
                    for row in rows
                ]

    def get_events_in_window_filtered(
        self,
        start_dt: datetime,
        end_dt: datetime,
        min_confidence: float = 0.0,
        max_events: int | None = None,
    ) -> list[Event]:
        """Get filtered events within date window.

        Matches SQLite semantics, including fallback to message_published_at and extracted_at.
        """

        params: list[object] = [start_dt, end_dt, min_confidence]
        limit_clause = ""
        if max_events is not None:
            limit_clause = " LIMIT %s"
            params.append(max_events)

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=extensions.cursor) as cur:
                cur.execute(
                    f"""
                    SELECT * FROM events
                    WHERE COALESCE(actual_start, actual_end, planned_start, planned_end, message_published_at, extracted_at) >= %s
                      AND COALESCE(actual_start, actual_end, planned_start, planned_end, message_published_at, extracted_at) <= %s
                      AND confidence >= %s
                    ORDER BY COALESCE(actual_start, actual_end, planned_start, planned_end, message_published_at, extracted_at) ASC
                    {limit_clause}
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description]
                return [
                    self._row_to_event(dict(zip(columns, row, strict=False)))
                    for row in rows
                ]

    def save_llm_call(self, metadata: LLMCallMetadata) -> None:
        """Save LLM call metadata.

        Args:
            metadata: Call metadata

        Raises:
            RepositoryError: On storage errors
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Note: LLMCallMetadata uses tokens_in/out, not prompt_tokens/completion_tokens
                # We map to database schema for consistency with SQLite
                cur.execute(
                    """
                    INSERT INTO llm_calls (
                        call_id, message_id, model, temperature, prompt_hash,
                        prompt_tokens, completion_tokens, total_tokens,
                        cost_usd, latency_ms, success, error_msg,
                        response_cached, response_json, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        f"{metadata.message_id}_{metadata.ts.isoformat()}",  # call_id
                        metadata.message_id,
                        metadata.model,
                        1.0,  # temperature (not in metadata)
                        metadata.prompt_hash,
                        metadata.tokens_in,  # Map to prompt_tokens
                        metadata.tokens_out,  # Map to completion_tokens
                        metadata.tokens_in + metadata.tokens_out,  # total_tokens
                        metadata.cost_usd,
                        metadata.latency_ms,
                        True,  # success (LLMCallMetadata doesn't track failures)
                        None,  # error_msg
                        metadata.cached,  # Map to response_cached
                        None,
                        metadata.ts,  # Map to created_at
                    ),
                )
                conn.commit()

    def get_daily_llm_cost(self, date: datetime) -> float:
        """Get total LLM cost for a day.

        Args:
            date: Date to check

        Returns:
            Total cost in USD

        Raises:
            RepositoryError: On storage errors
        """
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT COALESCE(SUM(cost_usd), 0.0) as total
                    FROM llm_calls
                    WHERE DATE(created_at) = DATE(%s)
                    """,
                (date,),
            )
            row = cur.fetchone()
            return float(row[0]) if row else 0.0

    def get_cached_llm_response(
        self, prompt_hash: str, *, max_age: timedelta | None = None
    ) -> str | None:
        """Get cached LLM response by prompt hash.

        Args:
            prompt_hash: SHA256 hash of prompt
            max_age: Optional TTL duration

        Returns:
            Cached JSON response or None

        Raises:
            RepositoryError: On storage errors
        """
        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT response_json, created_at
                    FROM llm_calls
                    WHERE prompt_hash = %s AND response_json IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                (prompt_hash,),
            )
            row = cast("tuple[str, datetime | None] | None", cur.fetchone())
            if not row:
                return None

            response_json, created_at = row

            if max_age is not None:
                if created_at is None:
                    logger.warning(
                        "llm_cache_missing_timestamp",
                        prompt_hash=prompt_hash[:12],
                    )
                    self.invalidate_llm_cache_entry(prompt_hash)
                    return None

                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)

                if created_at < datetime.now(tz=UTC) - max_age:
                    logger.info(
                        "llm_cache_entry_expired",
                        prompt_hash=prompt_hash[:12],
                        cached_at=created_at.isoformat(),
                    )
                    self.invalidate_llm_cache_entry(prompt_hash)
                    return None

            return response_json

    def save_llm_response(self, prompt_hash: str, response_json: str) -> None:
        """Persist structured LLM response for caching reuse."""

        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    UPDATE llm_calls
                    SET response_json = %s
                    WHERE call_id = (
                        SELECT call_id
                        FROM llm_calls
                        WHERE prompt_hash = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                    )
                    """,
                (response_json, prompt_hash),
            )
            conn.commit()

    def invalidate_llm_cache_entry(self, prompt_hash: str) -> None:
        """Clear cached payload without removing call records."""

        with self._get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    UPDATE llm_calls
                    SET response_json = NULL
                    WHERE prompt_hash = %s
                """,
                (prompt_hash,),
            )
            conn.commit()

    def get_last_processed_ts(
        self, channel: str, source_id: MessageSource | None = None
    ) -> float | None:
        """Get last processed timestamp for a channel from ingestion_state.

        Args:
            channel: Channel ID
            source_id: Message source (optional for backward compatibility)

        Returns:
            Last processed timestamp or None

        Raises:
            RepositoryError: On storage errors
        """
        # Use source-specific state table name from configuration
        table_name = self._get_state_table_name(source_id)
        logger.debug(f"Using state table: {table_name} for source: {source_id}")

        row: dict[str, Any] | None = None
        with self._get_connection() as conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        f"SELECT max_processed_ts FROM {table_name} WHERE channel_id = %s",
                        (channel,),
                    )
                    row = cur.fetchone()
                conn.commit()
            except PsycopgError as exc:
                conn.rollback()
                raise RepositoryError(
                    f"Failed to read ingestion timestamp for channel {channel}: {exc}"
                ) from exc

        if not row:
            return None

        last_ts = row.get("max_processed_ts")
        return float(last_ts) if last_ts is not None else None

    def update_last_processed_ts(
        self, channel: str, ts: float, source_id: MessageSource | None = None
    ) -> None:
        """Update last processed timestamp for a channel in ingestion_state.

        Args:
            channel: Channel ID
            ts: New timestamp
            source_id: Message source (optional for backward compatibility)

        Raises:
            RepositoryError: On storage errors
        """
        # Use source-specific state table name from configuration
        table_name = self._get_state_table_name(source_id)

        with self._get_connection() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {table_name} (channel_id, max_processed_ts, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (channel_id) DO UPDATE SET
                            max_processed_ts = EXCLUDED.max_processed_ts,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (channel, ts),
                    )
                conn.commit()
            except PsycopgError as exc:
                conn.rollback()
                raise RepositoryError(
                    f"Failed to update ingestion timestamp for channel {channel}: {exc}"
                ) from exc

    def get_last_processed_message_id(
        self, channel: str, source_id: MessageSource | None = None
    ) -> str | None:
        """Get last processed message ID for a Telegram channel.

        Args:
            channel: Channel ID (Telegram username)
            source_id: Message source (must be TELEGRAM for this method)

        Returns:
            Last processed message ID or None if first run

        Raises:
            RepositoryError: On storage errors
        """
        if source_id != MessageSource.TELEGRAM:
            raise RepositoryError(
                f"get_last_processed_message_id only supports TELEGRAM source, got {source_id}"
            )

        # Use source-specific state table name from configuration
        table_name = self._get_state_table_name(source_id)

        row: dict[str, Any] | None = None
        with self._get_connection() as conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        f"SELECT last_processed_message_id FROM {table_name} WHERE channel_id = %s",
                        (channel,),
                    )
                    row = cur.fetchone()
                conn.commit()
            except PsycopgError as exc:
                conn.rollback()
                raise RepositoryError(
                    f"Failed to read Telegram state for channel {channel}: {exc}"
                ) from exc

        return row["last_processed_message_id"] if row else None

    def update_last_processed_message_id(
        self, channel: str, message_id: str, source_id: MessageSource | None = None
    ) -> None:
        """Update last processed message ID for a Telegram channel.

        Args:
            channel: Channel ID (Telegram username)
            message_id: Message ID to set
            source_id: Message source (must be TELEGRAM for this method)

        Raises:
            RepositoryError: On storage errors
        """
        if source_id != MessageSource.TELEGRAM:
            raise RepositoryError(
                f"update_last_processed_message_id only supports TELEGRAM source, got {source_id}"
            )

        # Use source-specific state table name from configuration
        table_name = self._get_state_table_name(source_id)

        with self._get_connection() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {table_name} (channel_id, max_processed_ts, last_processed_message_id, updated_at)
                        VALUES (%s, 0, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (channel_id) DO UPDATE SET
                            max_processed_ts = 0,
                            last_processed_message_id = %s,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (channel, message_id, message_id),
                    )
                conn.commit()
            except PsycopgError as exc:
                conn.rollback()
                raise RepositoryError(
                    f"Failed to update Telegram state for channel {channel}: {exc}"
                ) from exc

    def query_events(self, criteria: "EventQueryCriteria") -> list[Event]:
        """Query events using structured criteria.

        Args:
            criteria: Query builder criteria object

        Returns:
            List of events matching criteria

        Raises:
            RepositoryError: On storage errors
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Build query parts
                    where_clause, where_params = criteria.to_where_clause()
                    order_clause = criteria.to_order_clause()
                    limit_clause, limit_params = criteria.to_limit_clause()

                    # Combine into full query (PostgreSQL uses %s placeholders)
                    query = f"""
                        SELECT * FROM events
                        WHERE {where_clause}
                        ORDER BY {order_clause}
                        {limit_clause}
                    """.strip()

                    # Execute with all parameters
                    all_params = where_params + limit_params
                    logger.debug(f"Executing query: {query}")
                    logger.debug(f"Parameters: {all_params}")
                    cur.execute(query, all_params)

                    rows = cur.fetchall()
                    return [self._row_to_event(dict(row)) for row in rows]

        except PsycopgError as exc:
            raise RepositoryError(f"Failed to query events: {exc}") from exc

    def query_candidates(
        self, criteria: "CandidateQueryCriteria"
    ) -> list[EventCandidate]:
        """Query event candidates using structured criteria.

        Args:
            criteria: Query builder criteria object

        Returns:
            List of event candidates matching criteria

        Raises:
            RepositoryError: On storage errors
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Build query parts
                    where_clause, where_params = criteria.to_where_clause()
                    order_clause = criteria.to_order_clause()
                    limit_clause, limit_params = criteria.to_limit_clause()

                    # Combine into full query (PostgreSQL uses %s placeholders)
                    query = f"""
                        SELECT * FROM event_candidates
                        WHERE {where_clause}
                        ORDER BY {order_clause}
                        {limit_clause}
                    """

                    # Execute with all parameters
                    all_params = where_params + limit_params
                    cur.execute(query, all_params)

                    rows = cur.fetchall()
                    return [self._row_to_candidate(dict(row)) for row in rows]

        except PsycopgError as exc:
            raise RepositoryError(f"Failed to query candidates: {exc}") from exc

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        """Serialize a vector to pgvector text format (avoids pgvector pkg)."""
        return "[" + ",".join(map(str, vector)) + "]"

    def save_event_relation(
        self,
        source_event_id: str,
        relation_type: str,
        target_event_id: str,
    ) -> None:
        """Persist a single event relation (idempotent on duplicates)."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO event_relations
                            (source_event_id, relation_type, target_event_id, created_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT DO NOTHING
                        """,
                        (source_event_id, relation_type, target_event_id),
                    )
                conn.commit()
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to save event relation: {exc}") from exc

    def save_event_embeddings(
        self,
        rows: list[tuple[str, str, str, list[float]]],
    ) -> None:
        """Upsert event embeddings into the pgvector-backed table."""
        if not rows:
            return
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO event_embeddings
                            (event_id, model, text_hash, embedding, created_at)
                        VALUES (%s, %s, %s, %s::vector, now())
                        ON CONFLICT (event_id) DO UPDATE SET
                            model = EXCLUDED.model,
                            text_hash = EXCLUDED.text_hash,
                            embedding = EXCLUDED.embedding,
                            created_at = EXCLUDED.created_at
                        """,
                        [
                            (
                                event_id,
                                model,
                                text_hash,
                                self._vector_literal(vector),
                            )
                            for event_id, model, text_hash, vector in rows
                        ],
                    )
                conn.commit()
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to save event embeddings: {exc}") from exc

    def get_events_missing_embedding(
        self,
        model: str,
        limit: int = 500,
    ) -> list[Event]:
        """Get non-archived events without a stored embedding for the model."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT e.* FROM events e
                        LEFT JOIN event_embeddings emb
                            ON emb.event_id = e.event_id AND emb.model = %s
                        WHERE emb.event_id IS NULL
                          AND COALESCE(e.review_status, 'needs_review') != 'archived'
                        ORDER BY e.extracted_at DESC
                        LIMIT %s
                        """,
                        (model, limit),
                    )
                    rows = cur.fetchall()
                    return [self._row_to_event(dict(row)) for row in rows]
        except PsycopgError as exc:
            raise RepositoryError(
                f"Failed to get events missing embedding: {exc}"
            ) from exc

    def get_event_embeddings(
        self,
        event_ids: list[str],
        model: str,
    ) -> dict[str, list[float]]:
        """Load stored embeddings for the given events."""
        if not event_ids:
            return {}
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT event_id, embedding::text AS embedding
                        FROM event_embeddings
                        WHERE model = %s AND event_id = ANY(%s)
                        """,
                        (model, event_ids),
                    )
                    rows = cur.fetchall()
                    return {
                        row["event_id"]: json.loads(row["embedding"]) for row in rows
                    }
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to get event embeddings: {exc}") from exc

    def get_events_by_cluster_key(self, cluster_key: str) -> list[Event]:
        """Get all events in the same cluster (same initiative), oldest first."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT * FROM events
                        WHERE cluster_key = %s
                        ORDER BY extracted_at ASC
                        """,
                        (cluster_key,),
                    )
                    rows = cur.fetchall()
                    return [self._row_to_event(dict(row)) for row in rows]
        except PsycopgError as exc:
            raise RepositoryError(
                f"Failed to get events by cluster key: {exc}"
            ) from exc

    def get_events_relating_to(
        self,
        event_ids: list[str],
        relation_type: str,
    ) -> list[Event]:
        """Get events that have a relation pointing AT the given events."""
        if not event_ids:
            return []
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT DISTINCT e.* FROM events e
                        JOIN event_relations r ON r.source_event_id = e.event_id
                        WHERE r.relation_type = %s AND r.target_event_id = ANY(%s)
                        ORDER BY e.extracted_at ASC
                        """,
                        (relation_type, event_ids),
                    )
                    rows = cur.fetchall()
                    return [self._row_to_event(dict(row)) for row in rows]
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to get relating events: {exc}") from exc

    def list_event_clusters(
        self,
        *,
        since: datetime | None = None,
        object_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List event clusters (stories) with aggregate stats."""
        try:
            query = """
                SELECT cluster_key,
                       COUNT(*) AS event_count,
                       MIN(COALESCE(message_published_at, extracted_at)) AS first_seen,
                       MAX(COALESCE(message_published_at, extracted_at)) AS last_seen,
                       MAX(importance) AS max_importance
                FROM events
                WHERE COALESCE(review_status, 'needs_review') != 'archived'
            """
            params: list[Any] = []
            if object_id is not None:
                query += " AND object_id = %s"
                params.append(object_id)
            query += " GROUP BY cluster_key"
            if since is not None:
                query += (
                    " HAVING MAX(COALESCE(message_published_at, extracted_at)) >= %s"
                )
                params.append(since)
            query += " ORDER BY last_seen DESC LIMIT %s"
            params.append(limit)

            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    return [dict(row) for row in rows]
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to list event clusters: {exc}") from exc

    def find_similar_events(
        self,
        vector: list[float],
        *,
        model: str,
        limit: int = 10,
        min_similarity: float = 0.0,
        extracted_after: datetime | None = None,
        exclude_event_id: str | None = None,
    ) -> list[tuple[Event, float]]:
        """Cosine search via pgvector exact scan (no ANN index needed at this scale)."""
        try:
            vector_literal = self._vector_literal(vector)
            query = """
                SELECT e.*,
                       1 - (emb.embedding <=> %s::vector) AS _similarity
                FROM events e
                JOIN event_embeddings emb ON emb.event_id = e.event_id
                WHERE emb.model = %s
                  AND 1 - (emb.embedding <=> %s::vector) >= %s
            """
            params: list[Any] = [vector_literal, model, vector_literal, min_similarity]
            if extracted_after is not None:
                query += " AND e.extracted_at >= %s"
                params.append(extracted_after)
            if exclude_event_id is not None:
                query += " AND e.event_id != %s"
                params.append(exclude_event_id)
            query += " ORDER BY emb.embedding <=> %s::vector ASC LIMIT %s"
            params.extend([vector_literal, limit])

            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    return [
                        (self._row_to_event(dict(row)), float(row["_similarity"]))
                        for row in rows
                    ]
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to find similar events: {exc}") from exc

    def record_object_suggestion(self, name_raw: str, event_id: str) -> None:
        """Upsert an unmatched object name into the suggestions queue."""
        name_normalized = name_raw.lower().strip()
        if not name_normalized:
            return
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        INSERT INTO object_suggestions
                            (name_normalized, name_raw_sample, occurrences,
                             sample_event_ids, status, created_at, updated_at)
                        VALUES (%s, %s, 1, %s::jsonb, 'pending', NOW(), NOW())
                        ON CONFLICT (name_normalized) DO UPDATE SET
                            occurrences = object_suggestions.occurrences + 1,
                            sample_event_ids = CASE
                                WHEN jsonb_array_length(
                                        object_suggestions.sample_event_ids) < 5
                                     AND NOT object_suggestions.sample_event_ids
                                         @> to_jsonb(%s::text)
                                THEN object_suggestions.sample_event_ids
                                     || to_jsonb(%s::text)
                                ELSE object_suggestions.sample_event_ids
                            END,
                            updated_at = NOW()
                        """,
                        (
                            name_normalized,
                            name_raw,
                            json.dumps([event_id]),
                            event_id,
                            event_id,
                        ),
                    )
                conn.commit()
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to record object suggestion: {exc}") from exc

    def list_object_suggestions(self, status: str = "pending") -> list[dict[str, Any]]:
        """List object suggestions with the given status, most frequent first."""
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT id, name_normalized, name_raw_sample, occurrences,
                               sample_event_ids, status, approved_object_id,
                               created_at, updated_at
                        FROM object_suggestions
                        WHERE status = %s
                        ORDER BY occurrences DESC, updated_at DESC
                        """,
                        (status,),
                    )
                    return [dict(row) for row in cur.fetchall()]
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to list object suggestions: {exc}") from exc

    def resolve_object_suggestion(
        self,
        suggestion_id: int,
        status: str,
        object_id: str | None = None,
    ) -> bool:
        """Mark a suggestion approved/rejected. Returns False if not found."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE object_suggestions
                        SET status = %s, approved_object_id = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (status, object_id, suggestion_id),
                    )
                    updated: bool = cur.rowcount > 0
                conn.commit()
                return updated
        except PsycopgError as exc:
            raise RepositoryError(
                f"Failed to resolve object suggestion: {exc}"
            ) from exc

    def update_event_review(
        self,
        event_id: str,
        review_status: ReviewLifecycleStatus,
        reviewed_by: str,
    ) -> bool:
        """Update review status of an event."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE events
                        SET review_status = %s, reviewed_by = %s, reviewed_at = NOW()
                        WHERE event_id = %s
                        """,
                        (review_status.value, reviewed_by, event_id),
                    )
                    updated: bool = cur.rowcount > 0
                conn.commit()
                return updated
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to update event review: {exc}") from exc

    def save_audit_entry(self, entry: EventAuditEntry) -> None:
        """Persist an audit log entry."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO event_audit_log
                            (audit_id, event_id, version, action, origin,
                             changes, actor, timestamp, note)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (audit_id) DO NOTHING
                        """,
                        (
                            str(entry.audit_id),
                            str(entry.event_id),
                            entry.version,
                            entry.action,
                            entry.origin.value,
                            json.dumps(entry.changes),
                            entry.actor,
                            entry.timestamp,
                            entry.note,
                        ),
                    )
                conn.commit()
        except PsycopgError as exc:
            raise RepositoryError(f"Failed to save audit entry: {exc}") from exc

    def save_telegram_messages(self, messages: list[TelegramMessage]) -> int:
        """Save Telegram messages to storage (idempotent upsert).

        Args:
            messages: List of Telegram messages

        Returns:
            Number of messages saved

        Raises:
            RepositoryError: On storage errors
        """
        if not messages:
            return 0

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    for msg in messages:
                        cur.execute(
                            """
                            INSERT INTO raw_telegram_messages (
                                message_id, channel, message_date, sender_id, sender_name,
                                text, text_norm, forward_from_channel, forward_from_message_id,
                                media_type, links_raw, links_norm, anchors, views, reply_count,
                                reactions, reactions_count, post_url, attachments_count,
                                files_count, bot_id, is_bot, reply_to_id, thread_id, has_file,
                                file_mime, ingested_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            ON CONFLICT (message_id) DO UPDATE SET
                                channel = EXCLUDED.channel,
                                message_date = EXCLUDED.message_date,
                                sender_id = EXCLUDED.sender_id,
                                sender_name = EXCLUDED.sender_name,
                                text = EXCLUDED.text,
                                text_norm = EXCLUDED.text_norm,
                                forward_from_channel = EXCLUDED.forward_from_channel,
                                forward_from_message_id = EXCLUDED.forward_from_message_id,
                                media_type = EXCLUDED.media_type,
                                links_raw = EXCLUDED.links_raw,
                                links_norm = EXCLUDED.links_norm,
                                anchors = EXCLUDED.anchors,
                                views = EXCLUDED.views,
                                reply_count = EXCLUDED.reply_count,
                                reactions = EXCLUDED.reactions,
                                reactions_count = EXCLUDED.reactions_count,
                                post_url = EXCLUDED.post_url,
                                attachments_count = EXCLUDED.attachments_count,
                                files_count = EXCLUDED.files_count,
                                bot_id = EXCLUDED.bot_id,
                                is_bot = EXCLUDED.is_bot,
                                reply_to_id = EXCLUDED.reply_to_id,
                                thread_id = EXCLUDED.thread_id,
                                has_file = EXCLUDED.has_file,
                                file_mime = EXCLUDED.file_mime,
                                ingested_at = EXCLUDED.ingested_at
                            """,
                            (
                                msg.message_id,
                                msg.channel,
                                msg.message_date,
                                msg.sender_id,
                                msg.sender_name,
                                msg.text,
                                msg.text_norm,
                                msg.forward_from_channel,
                                msg.forward_from_message_id,
                                msg.media_type,
                                json.dumps(msg.links_raw),
                                json.dumps(msg.links_norm),
                                json.dumps(msg.anchors),
                                msg.views,
                                msg.reply_count,
                                json.dumps(msg.reactions),
                                msg.reactions_count,
                                msg.post_url,
                                msg.attachments_count,
                                msg.files_count,
                                msg.bot_id,
                                msg.is_bot,
                                msg.reply_to_id,
                                msg.thread_id,
                                msg.has_file,
                                msg.file_mime,
                                msg.ingested_at,
                            ),
                        )

                    conn.commit()
                    count = len(messages)

            return count

        except PsycopgError as exc:
            raise RepositoryError(f"Failed to save Telegram messages: {exc}") from exc

    def get_telegram_messages(
        self, channel: str, limit: int = 100
    ) -> list[TelegramMessage]:
        """Get Telegram messages from storage.

        Args:
            channel: Channel username or ID (optional filter)
            limit: Maximum messages to return

        Returns:
            List of Telegram messages ordered by date DESC
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=extensions.cursor) as cur:
                    if channel:
                        cur.execute(
                            """
                            SELECT * FROM raw_telegram_messages
                            WHERE channel = %s
                            ORDER BY message_date DESC
                            LIMIT %s
                            """,
                            (channel, limit),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT * FROM raw_telegram_messages
                            ORDER BY message_date DESC
                            LIMIT %s
                            """,
                            (limit,),
                        )

                    rows = cur.fetchall()
                    # Get column names from cursor description
                    columns = [desc[0] for desc in cur.description]
                    return [
                        self._row_to_telegram_message(
                            dict(zip(columns, row, strict=False))
                        )
                        for row in rows
                    ]

        except PsycopgError as exc:
            raise RepositoryError(f"Failed to get Telegram messages: {exc}") from exc

    def _row_to_telegram_message(self, row: dict[str, Any]) -> TelegramMessage:
        """Convert database row to TelegramMessage.

        Args:
            row: Database row

        Returns:
            TelegramMessage instance
        """
        reactions_data_raw = row["reactions"] if row["reactions"] else {}
        if isinstance(reactions_data_raw, str):
            reactions_data = json.loads(reactions_data_raw)
        else:
            reactions_data = reactions_data_raw
        reactions_count = row.get("reactions_count") or sum(reactions_data.values())

        return TelegramMessage(
            message_id=row["message_id"],
            channel=row["channel"],
            message_date=row["message_date"],
            sender_id=row["sender_id"],
            sender_name=row["sender_name"],
            text=row["text"] or "",
            text_norm=row["text_norm"] or "",
            forward_from_channel=row["forward_from_channel"],
            forward_from_message_id=row["forward_from_message_id"],
            media_type=row["media_type"],
            links_raw=row["links_raw"] if row["links_raw"] else [],
            links_norm=row["links_norm"] if row["links_norm"] else [],
            anchors=row["anchors"] if row["anchors"] else [],
            views=row["views"] or 0,
            reply_count=row["reply_count"] or 0,
            reactions=reactions_data,
            reactions_count=reactions_count,
            post_url=row["post_url"],
            attachments_count=row.get("attachments_count") or 0,
            files_count=row.get("files_count") or 0,
            bot_id=row.get("bot_id"),
            is_bot=bool(row.get("is_bot")),
            reply_to_id=row.get("reply_to_id"),
            thread_id=row.get("thread_id"),
            is_reply=bool(row.get("reply_to_id")),
            has_file=bool(row.get("has_file")),
            file_mime=row.get("file_mime"),
            ingested_at=row["ingested_at"],
        )
