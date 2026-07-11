# QUALITY_BASELINE

## Scope
Baseline and post-remediation evidence for extraction quality KPIs.

## Baseline (existing DB state)
Measured on current DB (`events=118`, `messages=143`) before data re-extraction.

- `% multi-event messages`: **21.35%**
- `% future-like`: **6.78%**
- `% action=Other`: **6.78%**
- `% low utility summaries`: **0.00%** (current heuristic)
- `% low coverage summaries`: **8.47%**

Source: local metric computation script and policy functions.

## Post-remediation evidence

### Code-level enforcement now active
- Cardinality cap and primary/sub policy in extraction path:
  - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
  - [src/services/intra_message_postprocess.py](src/services/intra_message_postprocess.py)
- Planned-only without release evidence blocked:
  - [src/services/extraction_policy.py](src/services/extraction_policy.py)
  - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
- Non-event deterministic prefilter:
  - [src/services/extraction_policy.py](src/services/extraction_policy.py)
  - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
- Action normalization + summary semantic contract:
  - [src/services/extraction_policy.py](src/services/extraction_policy.py)
  - [src/use_cases/extract_events.py](src/use_cases/extract_events.py)

### Tests
Targeted policy regression suite:
- [tests/test_extraction_policy_enforcement.py](tests/test_extraction_policy_enforcement.py)
- [tests/test_intra_message_postprocess.py](tests/test_intra_message_postprocess.py)
- [tests/test_extract_events_caching.py](tests/test_extract_events_caching.py)
- [tests/test_extraction_time_completion_integration.py](tests/test_extraction_time_completion_integration.py)

Result: **12 passed**.

### Runtime metric framework
- Extraction now emits `pipeline_quality_snapshot` log with KPI percentages.
- Repeatable local/CI report script:
  - [scripts/quality_metrics_report.py](scripts/quality_metrics_report.py)

## Prospective effect estimate (policy simulation over current DB)
Applying new policy rules to current persisted rows (without full re-extraction) indicates:

- projected events after policy: **101** (from 118)
- projected `% future-like`: **0.00%**
- projected `% action=Other`: **5.94%**
- projected `% low coverage summaries`: **4.95%**

Note: this is a simulation over existing data, not a full backfill run with fresh extraction.

## Limitations
- Existing historical rows remain pre-remediation until backfill/re-extract.
- Utility heuristic is intentionally lightweight and should be calibrated with review feedback.
