"""Deterministic extraction policy helpers.

These rules enforce P0/P1 quality constraints independent of prompt behavior.
"""

from __future__ import annotations

import re

from src.domain.models import ActionType, Event

_RELEASE_FACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(release|released|shipped|launched|rolled\s*out|enabled|deployed|live|available\s+now|ga|beta\s+opened|completed)\b", re.IGNORECASE),
    re.compile(r"\b(в\s+проде|в\s+продакшене|зарелизили|выпустили|запустили|задеплоили|включили|доступно\s+сейчас|завершен|завершили)\b", re.IGNORECASE),
)

_NON_EVENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(seminar|webinar|workshop|meeting)\b", re.IGNORECASE),
    re.compile(r"\b(research|investigation|exploration)\b", re.IGNORECASE),
    re.compile(r"\b(request\s+for\s+help|can\s+someone\s+help|need\s+help|help\s+thread|support\s+thread|question\s+thread)\b", re.IGNORECASE),
    re.compile(r"\b(семинар|вебинар|воркшоп)\b", re.IGNORECASE),
    re.compile(r"\b(исследовани|рисерч|изучаем|расследовани)\b", re.IGNORECASE),
    re.compile(r"\b(нужна\s+помощь|кто\s+может\s+помочь|help\s*please|вопрос\s+в\s+тред)\b", re.IGNORECASE),
)

_T_PRODUCT_RESCUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(policy|decision|rule|gating|gate|milestone|workflow|compliance|kyc|kyt|enabled|deployed|launched|live|rolled\s*out)\b", re.IGNORECASE),
    re.compile(r"\b(политик|решени|правил|гейт|майлстоун|воркфлоу|комплаенс|kyc|kyt|включ|задепло|запущ|в\s+проде|в\s+продакшене)\b", re.IGNORECASE),
)

_T_PRODUCT_STRONG_CHANGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(delist|delisted|disable|disabled|remove|removed|roll\s?back|rollback|zero\s+fee|fee\s*[:=]\s*0)\b", re.IGNORECASE),
    re.compile(r"\b(делист|отключ|убра(ть|ли)|обнул|откат|запрет|останов|комисси\w*\s*(0|ноль))\b", re.IGNORECASE),
)

_T_PRODUCT_STRONG_CHANGE_STEMS: tuple[str, ...] = (
    "delist",
    "disable",
    "removed",
    "rollback",
    "делист",
    "отключ",
    "убра",
    "обнул",
    "откат",
    "запрет",
    "останов",
)

_CHANGE_TERMS: tuple[str, ...] = (
    "launched",
    "launch",
    "release",
    "released",
    "deployed",
    "completed",
    "enabled",
    "rolled out",
    "introduced",
    "increased",
    "decreased",
    "disabled",
    "restored",
    "запущ",
    "выпущ",
    "включ",
    "отключ",
    "увелич",
    "снижен",
)

_EFFECT_TERMS: tuple[str, ...] = (
    "impact",
    "reduce",
    "improve",
    "increase",
    "decrease",
    "enable",
    "allow",
    "risk",
    "matters",
    "growth",
    "retention",
    "conversion",
    "сниж",
    "увелич",
    "влиян",
    "эффект",
    "важно",
)

_ACTIONS_IMPLYING_CHANGE: tuple[ActionType, ...] = (
    ActionType.LAUNCH,
    ActionType.DEPLOY,
    ActionType.MIGRATION,
    ActionType.MOVE,
    ActionType.ROLLBACK,
    ActionType.POLICY,
    ActionType.AB_TEST,
    ActionType.INCIDENT,
)


def has_release_fact_evidence(text: str) -> bool:
    """Return True when text contains factual release/change wording."""

    for pattern in _RELEASE_FACT_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _has_strong_change_signal(text: str) -> bool:
    normalized = re.sub(r"[`*_~]", " ", text or "")
    if any(pattern.search(normalized) for pattern in _T_PRODUCT_STRONG_CHANGE_PATTERNS):
        return True

    lower = normalized.lower()
    return any(stem in lower for stem in _T_PRODUCT_STRONG_CHANGE_STEMS)


def is_non_event_message(text: str) -> bool:
    """Return True when message intent is clearly non-event."""

    if _has_strong_change_signal(text):
        return False

    for pattern in _NON_EVENT_PATTERNS:
        if pattern.search(text):
            return True
    return False


def is_t_product_rescue_candidate(text: str) -> bool:
    """Heuristic for second-pass extraction in t-product channel.

    Candidate must carry concrete change signals and not be a clear non-event.
    """

    if is_non_event_message(text):
        return False

    normalized = re.sub(r"[`*_~]", " ", text)

    if _has_strong_change_signal(normalized):
        return True

    has_keyword = any(pattern.search(normalized) for pattern in _T_PRODUCT_RESCUE_PATTERNS)
    return has_keyword and (
        has_release_fact_evidence(normalized)
        or re.search(
            r"\b(completed|implemented|restored|updated|заверш|внедр|восстанов|обнов)\b",
            normalized,
            re.IGNORECASE,
        )
        is not None
    )


def normalize_action(raw_action: str) -> ActionType:
    """Map free-form action labels to canonical enum values."""

    token = (raw_action or "").strip().lower()
    mapping: dict[str, ActionType] = {
        "launch": ActionType.LAUNCH,
        "launched": ActionType.LAUNCH,
        "release": ActionType.LAUNCH,
        "released": ActionType.LAUNCH,
        "deploy": ActionType.DEPLOY,
        "deployed": ActionType.DEPLOY,
        "enable": ActionType.DEPLOY,
        "enabled": ActionType.DEPLOY,
        "rollout": ActionType.DEPLOY,
        "rolled out": ActionType.DEPLOY,
        "migration": ActionType.MIGRATION,
        "migrate": ActionType.MIGRATION,
        "move": ActionType.MOVE,
        "rollback": ActionType.ROLLBACK,
        "rolled back": ActionType.ROLLBACK,
        "policy": ActionType.POLICY,
        "campaign": ActionType.CAMPAIGN,
        "incident": ActionType.INCIDENT,
        "a/b test": ActionType.AB_TEST,
        "ab test": ActionType.AB_TEST,
        "webinar": ActionType.WEBINAR,
        "rca": ActionType.RCA,
    }
    mapped = mapping.get(token)
    if mapped is not None:
        return mapped

    try:
        return ActionType(raw_action)
    except ValueError:
        return ActionType.OTHER


def summary_has_change(summary: str) -> bool:
    lower = (summary or "").lower()
    return any(term in lower for term in _CHANGE_TERMS)


def summary_has_effect(summary: str, why_it_matters: str | None) -> bool:
    if why_it_matters and why_it_matters.strip():
        return True
    lower = (summary or "").lower()
    return any(term in lower for term in _EFFECT_TERMS)


def action_implies_change(action: ActionType) -> bool:
    """Return True when action inherently expresses a concrete change."""

    return action in _ACTIONS_IMPLYING_CHANGE


def summary_contract_components(event: Event) -> tuple[bool, bool, bool]:
    """Return (has_change, has_scope, has_effect) contract components."""

    has_change = summary_has_change(event.summary) or action_implies_change(event.action)
    has_scope = bool((event.object_name_raw or "").strip())
    has_effect = summary_has_effect(event.summary, event.why_it_matters)
    return has_change, has_scope, has_effect


def summary_meets_contract(event: Event, *, require_effect: bool = True) -> bool:
    """Validate summary contract semantics.

    Default (strict): require change + scope + effect.
    Balanced mode: require change + scope only, effect becomes a soft quality signal.
    """

    has_change, has_scope, has_effect = summary_contract_components(event)
    if require_effect:
        return has_change and has_scope and has_effect
    return has_change and has_scope


def is_future_like_without_evidence(event: Event, message_text: str) -> bool:
    """Block planned-only timeline candidates without explicit release evidence."""

    has_actual = event.actual_start is not None or event.actual_end is not None
    has_planned = event.planned_start is not None or event.planned_end is not None
    if has_actual:
        return False
    if not has_planned:
        return False
    return not has_release_fact_evidence(message_text)


def is_low_utility_summary(event: Event) -> bool:
    """Heuristic low-utility summary marker."""

    score = 0
    if len((event.summary or "").strip()) >= 80:
        score += 1
    if summary_has_change(event.summary):
        score += 1
    if (event.object_name_raw or "").strip():
        score += 1
    if summary_has_effect(event.summary, event.why_it_matters):
        score += 1
    return score <= 2


def is_low_coverage_summary(event: Event, raw_text: str) -> bool:
    """Heuristic marker for weak summary coverage relative to source text."""

    summary = (event.summary or "").lower()
    text = (raw_text or "").lower()
    if not summary:
        return True
    if len(text) < 120:
        return False
    key_tokens = [t for t in re.findall(r"[a-zA-Zа-яА-Я0-9]{4,}", summary)[:12]]
    if not key_tokens:
        return True
    overlap = sum(1 for token in key_tokens if token in text)
    return overlap / len(key_tokens) < 0.5
