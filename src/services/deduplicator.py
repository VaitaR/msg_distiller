"""Event deduplication service.

Rules:
1. Events from same message_id NEVER merge
2. Inter-message merge if:
   - Anchor/link overlap
   - Date delta <= 48 hours (configurable)
   - Rendered title similarity >= 0.8 (configurable)

New Structure:
- cluster_key: Initiative-level grouping (without status/time/environment)
- dedup_key: Specific instance (with status/time/environment)
"""

import hashlib
from datetime import datetime

from rapidfuzz import fuzz

from src.domain.deduplication_constants import (
    DEFAULT_DATE_WINDOW_HOURS,
    DEFAULT_TITLE_SIMILARITY,
    SAME_MESSAGE_NO_MERGE,
    SEMANTIC_TITLE_SIMILARITY,
)
from src.domain.models import Event, EventRelation, RelationType
from src.services.title_renderer import TitleRenderer

_DEFAULT_TITLE_RENDERER = TitleRenderer()


def generate_cluster_key(event: Event) -> str:
    """Generate cluster key for initiative-level grouping.

    Cluster key groups events from the same initiative regardless of status/time/environment.
    Based on: action + object_id (or object_name_raw) + top_anchor

    Args:
        event: Event to generate key for

    Returns:
        SHA1 hex digest

    Example:
        >>> evt = Event(action="Launch", object_name_raw="Stocks", ...)
        >>> generate_cluster_key(evt)
        'b2d4c1a9...'
    """
    # Use object_id if available, fallback to raw name
    object_key = event.object_id or event.object_name_raw.lower().strip()

    # Top anchor (first one if available, else empty)
    top_anchor = event.anchors[0] if event.anchors else ""

    # Concatenate: source + action + object + anchor
    key_material = (
        f"{event.source_id.value}||{event.action.value}||{object_key}||{top_anchor}"
    )
    return hashlib.sha1(key_material.encode("utf-8")).hexdigest()


def generate_dedup_key(event: Event) -> str:
    """Generate dedup key for specific instance identification.

    Dedup key includes status/time/environment to distinguish different instances
    of the same initiative (e.g., planned vs started vs completed).

    Based on: cluster_key + status + primary_time + environment

    Args:
        event: Event to generate key for

    Returns:
        SHA1 hex digest

    Example:
        >>> evt = Event(status="started", ...)
        >>> generate_dedup_key(evt)
        'a3f2b1c0...'
    """
    # Start with cluster key
    cluster = generate_cluster_key(event)

    # Add status
    status_val = event.status.value

    # Primary time (prefer actual, fallback to planned)
    primary_time = (
        event.actual_start
        or event.actual_end
        or event.planned_start
        or event.planned_end
    )
    time_str = primary_time.isoformat() if primary_time else "no-time"

    # Environment
    env_val = event.environment.value

    # Concatenate
    key_material = f"{cluster}||{status_val}||{time_str}||{env_val}"
    return hashlib.sha1(key_material.encode("utf-8")).hexdigest()


def has_overlap(list1: list[str], list2: list[str]) -> bool:
    """Check if two lists have any common elements.

    Args:
        list1: First list
        list2: Second list

    Returns:
        True if intersection is non-empty

    Example:
        >>> has_overlap(["a", "b"], ["b", "c"])
        True
        >>> has_overlap(["a"], ["b"])
        False
    """
    return bool(set(list1) & set(list2))


def should_merge_events(
    event1: Event,
    event2: Event,
    date_window_hours: int = DEFAULT_DATE_WINDOW_HOURS,
    title_similarity_threshold: float = DEFAULT_TITLE_SIMILARITY,
    title_renderer: TitleRenderer | None = None,
) -> bool:
    """Determine if two events should be merged.

    Two merge paths:
    1. **Anchor path** (standard): events share anchor/link overlap + date window
       + rendered-title similarity ≥ threshold (0.80).
    2. **Semantic path** (fallback): no anchor overlap, but object_name_raw
       token-set similarity ≥ SEMANTIC_TITLE_SIMILARITY (0.85). Catches same-
       initiative announcements posted without Jira/PR references.

    Rules:
    - Same message_id: NO merge (Rule 1)
    - Different source_id: NO merge
    - Date delta > date_window_hours: NO merge (applied on both paths)

    Args:
        event1: First event
        event2: Second event
        date_window_hours: Maximum date difference in hours (default: 48)
        title_similarity_threshold: Fuzzy similarity for anchor path (default: 0.8)
        title_renderer: Optional title renderer instance

    Returns:
        True if events should merge

    Example:
        >>> evt1 = Event(message_id="m1", object_name_raw="loyalty program in Wallet", ...)
        >>> evt2 = Event(message_id="m2", object_name_raw="wallet loyalty program v1.0", ...)
        >>> should_merge_events(evt1, evt2)  # semantic path, no anchors
        True
    """
    # Rule 1: Same message_id = NO merge
    if SAME_MESSAGE_NO_MERGE and event1.message_id == event2.message_id:
        return False

    # Only merge events from the same source
    if event1.source_id != event2.source_id:
        return False

    # Check time delta first (applies to both merge paths)
    time1 = (
        event1.actual_start
        or event1.actual_end
        or event1.planned_start
        or event1.planned_end
    )
    time2 = (
        event2.actual_start
        or event2.actual_end
        or event2.planned_start
        or event2.planned_end
    )
    if time1 and time2:
        date_delta = abs((time1 - time2).total_seconds() / 3600)
        if date_delta > date_window_hours:
            return False

    # Check anchor/link overlap
    combined_anchors1 = event1.anchors + event1.links
    combined_anchors2 = event2.anchors + event2.links
    has_anchor_overlap = has_overlap(combined_anchors1, combined_anchors2)

    renderer = title_renderer or _DEFAULT_TITLE_RENDERER

    if has_anchor_overlap:
        # --- Anchor path (standard) ---
        title1 = renderer.render_canonical_title(event1)
        title2 = renderer.render_canonical_title(event2)
        similarity: float = fuzz.ratio(title1, title2) / 100.0
        return similarity >= title_similarity_threshold
    elif not combined_anchors1 and not combined_anchors2:
        # --- Semantic path (fallback, stricter threshold) ---
        # Only fires when NEITHER event has any anchor or link: if they have
        # different non-overlapping Jira/PR/URL anchors they are likely
        # separate tickets and should NOT be auto-merged.
        # e.g. "loyalty program in Wallet" vs "wallet loyalty program v1.0"
        raw_sim: float = (
            fuzz.token_set_ratio(
                event1.object_name_raw.lower().strip(),
                event2.object_name_raw.lower().strip(),
            )
            / 100.0
        )
        return raw_sim >= SEMANTIC_TITLE_SIMILARITY
    else:
        # One or both events have anchors that don't overlap — likely different
        # tickets; don't merge.
        return False


def merge_events(event1: Event, event2: Event) -> tuple[Event, Event]:
    """Merge two events into (survivor, archived_absorbed).

    Strategy:
    - Union: links, source_channels, anchors, impact_area, impact_type
    - Max: confidence, importance
    - Keep: event1's core attributes (title slots, status, times)
    - Survivor gets an ABSORBED_FROM relation pointing to event2
    - event2 is returned as archived with origin=SYSTEM_MERGE

    Args:
        event1: Primary event (survivor, keeps core attributes and event_id)
        event2: Secondary event (absorbed, will be archived)

    Returns:
        Tuple of (survivor_event, archived_absorbed_event)

    Example:
        >>> survivor, absorbed = merge_events(evt1, evt2)
        >>> survivor.relations[0].relation_type
        RelationType.ABSORBED_FROM
        >>> absorbed.review_status
        ReviewLifecycleStatus.ARCHIVED
    """
    from src.domain.models import EventOrigin, ReviewLifecycleStatus

    # Union of lists (deduplicated)
    merged_links = list(set(event1.links + event2.links))[:3]  # Max 3
    merged_channels = list(set(event1.source_channels + event2.source_channels))
    merged_anchors = list(set(event1.anchors + event2.anchors))
    merged_impact_area = list(set(event1.impact_area + event2.impact_area))[:3]  # Max 3
    merged_impact_type = list(set(event1.impact_type + event2.impact_type))
    merged_qualifiers = list(set(event1.qualifiers + event2.qualifiers))[:2]  # Max 2

    # Max values
    max_confidence = max(event1.confidence, event2.confidence)
    max_importance = max(event1.importance, event2.importance)

    # Earliest time values (prefer earlier dates for event start times)
    def earliest_time(t1: datetime | None, t2: datetime | None) -> datetime | None:
        if t1 is None:
            return t2
        if t2 is None:
            return t1
        return min(t1, t2)

    # ABSORBED_FROM relation: survivor records which event it absorbed
    absorbed_relation = EventRelation(
        relation_type=RelationType.ABSORBED_FROM,
        target_event_id=event2.event_id,
    )
    survivor_relations = [
        r
        for r in event1.relations
        if r.relation_type != RelationType.ABSORBED_FROM
        or r.target_event_id != event2.event_id
    ] + [absorbed_relation]

    # Create merged event (keeping event1 as base)
    merged = Event(
        # Identification
        event_id=event1.event_id,  # Keep primary ID
        message_id=event1.message_id,
        source_channels=merged_channels,
        extracted_at=event1.extracted_at,
        source_id=event1.source_id,
        # Title slots (keep event1's)
        action=event1.action,
        object_id=event1.object_id,
        object_name_raw=event1.object_name_raw,
        qualifiers=merged_qualifiers,
        stroke=event1.stroke or event2.stroke,
        anchor=event1.anchor or event2.anchor,
        # Classification (keep event1's)
        category=event1.category,
        status=event1.status,
        change_type=event1.change_type,
        environment=event1.environment,
        severity=event1.severity or event2.severity,
        # Time fields (choose earliest times)
        planned_start=earliest_time(event1.planned_start, event2.planned_start),
        planned_end=earliest_time(event1.planned_end, event2.planned_end),
        actual_start=earliest_time(event1.actual_start, event2.actual_start),
        actual_end=earliest_time(event1.actual_end, event2.actual_end),
        time_source=event1.time_source,
        time_confidence=max(event1.time_confidence, event2.time_confidence),
        # Content (keep event1's primary, merge lists)
        summary=event1.summary,
        why_it_matters=event1.why_it_matters or event2.why_it_matters,
        links=merged_links,
        anchors=merged_anchors,
        impact_area=merged_impact_area,
        impact_type=merged_impact_type,
        # Quality (max)
        confidence=max_confidence,
        importance=max_importance,
        # Clustering (keep event1's)
        cluster_key=event1.cluster_key,
        dedup_key=event1.dedup_key,
        relations=survivor_relations,
        # Review lifecycle: keep event1's status, bump version, mark as system_merge
        review_status=event1.review_status,
        reviewed_by=event1.reviewed_by,
        reviewed_at=event1.reviewed_at,
        version=event1.version + 1,
        origin=EventOrigin.SYSTEM_MERGE,
    )

    refreshed_key = generate_dedup_key(merged)
    if refreshed_key != merged.dedup_key:
        merged = merged.model_copy(update={"dedup_key": refreshed_key})

    # Create archived copy of the absorbed event
    archived_absorbed = event2.model_copy(
        update={
            "review_status": ReviewLifecycleStatus.ARCHIVED,
            "origin": EventOrigin.SYSTEM_MERGE,
            "version": event2.version + 1,
        }
    )

    return merged, archived_absorbed


def find_merge_candidates(
    new_event: Event,
    existing_events: list[Event],
    date_window_hours: int = DEFAULT_DATE_WINDOW_HOURS,
    title_similarity_threshold: float = DEFAULT_TITLE_SIMILARITY,
    title_renderer: TitleRenderer | None = None,
) -> list[Event]:
    """Find existing events that should merge with new event.

    Args:
        new_event: Event to check
        existing_events: Pool of existing events
        date_window_hours: Date window for consideration
        title_similarity_threshold: Fuzzy match threshold

    Returns:
        List of events that should merge

    Example:
        >>> new_evt = Event(...)
        >>> existing = [Event(...), Event(...)]
        >>> candidates = find_merge_candidates(new_evt, existing)
        >>> len(candidates)
        1
    """
    candidates = []

    for existing in existing_events:
        if should_merge_events(
            new_event,
            existing,
            date_window_hours=date_window_hours,
            title_similarity_threshold=title_similarity_threshold,
            title_renderer=title_renderer,
        ):
            candidates.append(existing)

    return candidates


def deduplicate_event_list(
    events: list[Event],
    date_window_hours: int = DEFAULT_DATE_WINDOW_HOURS,
    title_similarity_threshold: float = DEFAULT_TITLE_SIMILARITY,
    title_renderer: TitleRenderer | None = None,
) -> tuple[list[Event], list[Event]]:
    """Deduplicate a list of events in-memory.

    Returns:
        Tuple of (survivors, absorbed_events) where absorbed_events have
        been marked with review_status=ARCHIVED and origin=SYSTEM_MERGE.
        Both lists must be persisted by the caller.

    Args:
        events: List of events to deduplicate
        date_window_hours: Date window
        title_similarity_threshold: Fuzzy threshold for anchor path

    Example:
        >>> survivors, absorbed = deduplicate_event_list(events)
        >>> len(survivors) + len(absorbed) == len(events)
        True
    """
    if not events:
        return [], []

    # Helper to get primary time for sorting
    def get_primary_time(event: Event) -> datetime:
        return (
            event.actual_start
            or event.actual_end
            or event.planned_start
            or event.planned_end
            or event.extracted_at
        )

    # Sort by date to process chronologically
    sorted_events = sorted(events, key=get_primary_time)

    deduplicated: list[Event] = []
    absorbed_events: list[Event] = []
    processed_dedup_keys: set[str] = set()

    for event in sorted_events:
        # Check if already processed (by dedup_key)
        if event.dedup_key in processed_dedup_keys:
            continue

        # Find merge candidates in already processed events
        merge_candidates = find_merge_candidates(
            event,
            deduplicated,
            date_window_hours=date_window_hours,
            title_similarity_threshold=title_similarity_threshold,
            title_renderer=title_renderer,
        )

        if merge_candidates:
            # Merge with first candidate, remove it, add merged
            target = merge_candidates[0]
            deduplicated.remove(target)
            processed_dedup_keys.discard(target.dedup_key)

            merged, archived = merge_events(target, event)
            absorbed_events.append(archived)
            deduplicated.append(merged)
            processed_dedup_keys.add(merged.dedup_key)
        else:
            # No merge needed, add as new
            deduplicated.append(event)
            processed_dedup_keys.add(event.dedup_key)

    return deduplicated, absorbed_events
