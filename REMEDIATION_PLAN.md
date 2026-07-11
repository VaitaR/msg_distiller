# REMEDIATION_PLAN

## Prioritized issues and root causes

## P0

### 1) Multi-event over-extraction per raw message
- Root cause:
  - LLM can emit up to K events and chunking can amplify extraction fan-out.
  - Existing intra-message dedup did not enforce strict primary/sub policy.
- Enforcement points:
  - [src/services/intra_message_postprocess.py](src/services/intra_message_postprocess.py)
  - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
- Fix strategy:
  - Hard-cap to max 2 events/message.
  - Enforce `1 primary + optional 1 tightly-bound sub-event`.

### 2) Planned-only events entering timeline
- Root cause:
  - Planned timestamps can be extracted and saved even without explicit release evidence.
- Enforcement points:
  - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
  - [src/services/extraction_policy.py](src/services/extraction_policy.py)
- Fix strategy:
  - Reject planned-only (`planned_*` with no `actual_*`) unless raw message has explicit release fact evidence.

### 3) Non-event leakage
- Root cause:
  - Prompt-only non-event detection is non-deterministic.
- Enforcement points:
  - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
  - [src/services/extraction_policy.py](src/services/extraction_policy.py)
- Fix strategy:
  - Deterministic pre-filter for seminar/research/request/help-thread intents (unless explicit release evidence exists).

## P1

### 4) `action=Other` too high
- Root cause:
  - strict enum parse fallback to `Other` without normalization.
- Enforcement points:
  - `convert_llm_event_to_domain()` in [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
- Fix strategy:
  - Canonical action normalization map before enum fallback.

### 5) Summary contract missing fields
- Root cause:
  - structural validator checked non-empty summary, not semantic `change + scope + effect`.
- Enforcement points:
  - [src/services/extraction_policy.py](src/services/extraction_policy.py)
  - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
- Fix strategy:
  - Pre-save semantic contract check.
  - Reject events that fail summary contract.

## P2

### 6) Missing recurring quality metrics framework
- Root cause:
  - No dedicated quality KPI snapshot on extraction path.
- Enforcement points:
  - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
  - [scripts/quality_metrics_report.py](scripts/quality_metrics_report.py)
- Fix strategy:
  - Emit `pipeline_quality_snapshot` each extraction batch.
  - Add CLI script for repeatable local/CI metric extraction.

## Why these enforcement points

These are the narrowest deterministic choke points before persistence:
- all extracted events pass through extraction post-processing and save,
- policy checks here are source-agnostic (Slack/Telegram shared path),
- test coverage can target this path without end-to-end external dependencies.
