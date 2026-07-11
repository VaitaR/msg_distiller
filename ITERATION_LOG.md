# ITERATION_LOG

## Iteration 0 — Recon

### Hypothesis
The most reliable place to fix P0/P1 is extraction post-processing + pre-save policy guards, not prompts alone.

### Evidence gathered
- Runtime flow mapped in [SYSTEM_MAP.md](SYSTEM_MAP.md).
- Extraction fan-out and save path identified in [src/use_cases/extract_events.py](src/use_cases/extract_events.py).
- Intra-message selection existed but no explicit primary/sub guard in [src/services/intra_message_postprocess.py](src/services/intra_message_postprocess.py).
- Action fallback to `Other` identified in `convert_llm_event_to_domain()` in [src/use_cases/extract_events.py](src/use_cases/extract_events.py).
- No deterministic non-event/future-only guard before save.

### Subagents used
- `remediation-planner`
- `researcher` (policy audit)
- `researcher` (schema/extraction specialist)
- `test-recovery-regression`
- `observability-telemetry`

### Next step
Implement P0 containment with deterministic policy module and extraction gate changes.

---

## Iteration 1 — P0 containment

### Hypothesis
If we enforce cardinality + future-only rejection + non-event prefilter in extraction save path, P0 leakage is contained regardless of prompt drift.

### Files changed
- Added [src/services/extraction_policy.py](src/services/extraction_policy.py)
- Updated [src/services/intra_message_postprocess.py](src/services/intra_message_postprocess.py)
- Updated [src/use_cases/extract_events.py](src/use_cases/extract_events.py)

### Key changes
- Non-event prefilter for seminar/research/request/help-thread.
- Planned-only events rejected unless explicit release evidence exists in raw text.
- Hard cap enforced to `<=2` per message.
- Primary + optional tightly-bound sub-event policy.

### Tests added/updated
- Updated [tests/test_extraction_time_completion_integration.py](tests/test_extraction_time_completion_integration.py)
- Updated [tests/test_intra_message_postprocess.py](tests/test_intra_message_postprocess.py)
- Added [tests/test_extraction_policy_enforcement.py](tests/test_extraction_policy_enforcement.py)

### Validation results
- Targeted regression run passed:
  - `12 passed`
  - command covered extraction caching/time completion/policy/postprocess tests.

### Residual risks
- Historical events already in DB are not backfilled automatically.
- Tight-binding heuristic can still keep occasional weak second event.

---

## Iteration 2 — P1 semantic tightening

### Hypothesis
Action normalization + summary semantic contract in save path reduce `Other` and weak summaries.

### Files changed
- Updated [src/services/extraction_policy.py](src/services/extraction_policy.py)
- Updated [src/use_cases/extract_events.py](src/use_cases/extract_events.py)

### Key changes
- Deterministic `normalize_action()` mapping before enum fallback.
- Summary contract gate requires `change + scope + effect`.

### Validation
- New policy tests included action normalization and summary-adjacent gating scenarios.
- Targeted test suite remained green.

### Residual risks
- Existing persisted data may still show pre-remediation `Other`/weak summaries.

---

## Iteration 3 — P2 quality instrumentation

### Hypothesis
If extraction emits quality snapshots and we provide a repeatable report script, recurring quality can be inspected in local/CI.

### Files changed
- Updated [src/use_cases/extract_events.py](src/use_cases/extract_events.py)
- Added [scripts/quality_metrics_report.py](scripts/quality_metrics_report.py)

### Key changes
- Aggregated extraction batch KPIs:
  - `% multi-event messages`
  - `% future-like`
  - `% action=Other`
  - `% low utility summaries`
  - `% low coverage summaries`
- Added report script to compute the same metrics from DB.

### Validation
- Script execution successful and prints required KPI fields.

### Residual risks
- Worker-only path should be validated for consistent KPI emission parity (if deployed separately).

---

## Iteration 4 — Reassessment

### Outcome
- P0 policy enforcement is code-level and test-covered in extraction path.
- P1 materially improved via normalization + summary contract.
- P2 has a usable metrics framework (runtime snapshot + report script).

### Next high-value cleanup
- Add historical cleanup/backfill command to re-evaluate existing events under new policy.
- Consider timeline endpoint policy filter parity for pre-remediation legacy rows.
