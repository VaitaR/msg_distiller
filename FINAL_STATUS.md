# FINAL_STATUS

## P0 status: **partial (code-enforced for new extraction path)**

### What is fixed
- Hard cardinality enforcement (`1 primary + optional 1 sub`) in extraction post-process.
- Planned-only events without explicit release evidence are blocked before persistence.
- Non-event intents (seminar/research/request/help-thread) are pre-filtered before LLM extraction.

### Evidence
- [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
- [src/services/intra_message_postprocess.py](src/services/intra_message_postprocess.py)
- [src/services/extraction_policy.py](src/services/extraction_policy.py)
- [tests/test_extraction_policy_enforcement.py](tests/test_extraction_policy_enforcement.py)

### Why partial
- Historical events already in DB are not auto-cleaned.
- Timeline endpoint for legacy records is not yet backfilled with new policy outcomes.

---

## P1 status: **partial**

### What is fixed
- Action normalization improved before enum fallback to reduce `Other` on new extractions.
- Summary semantic contract (`change + scope + effect`) enforced before save.

### Evidence
- [src/services/extraction_policy.py](src/services/extraction_policy.py)
- [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
- [tests/test_extraction_policy_enforcement.py](tests/test_extraction_policy_enforcement.py)

### Remaining gap
- `action=Other < 2%` target is not yet guaranteed on legacy data.
- Additional synonym expansion may still be needed per channel/source vocabulary.

---

## P2 status: **closed (framework available and runnable)**

### What is fixed
- Runtime KPI snapshot emitted from extraction batches.
- Local/CI-friendly metrics report script added.

### Evidence
- [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
- [scripts/quality_metrics_report.py](scripts/quality_metrics_report.py)
- [QUALITY_BASELINE.md](QUALITY_BASELINE.md)

---

## Remaining risks
- Backfill needed to fully align existing timeline inventory with new P0/P1 policy.
- Worker-only deployments should confirm the same KPI snapshot visibility and thresholds.

## Recommended next fixes
1. Add an explicit backfill/revalidation command to re-score existing events under new policy.
2. Add API-level optional strict timeline filter for legacy rows (`planned-only` suppression).
3. Expand action synonym map with production telemetry from unknown/Other occurrences.
4. Add CI check on `scripts/quality_metrics_report.py` thresholds (warn/fail gates).

## Clean shortlist for production timeline policy
- Keep events that:
  - pass summary contract,
  - are not non-event intents,
  - are not planned-only without explicit release evidence,
  - satisfy cardinality policy per message.
- Prefer one principal event entry per source message; allow one tightly-bound sub-event only.
