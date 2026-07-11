# Quality Post-Analysis — 2026-04-17

## Scope
Hard historical Slack reprocessing under updated extraction policies.

## Execution Summary
- Created DB backup: `data/slack_events.pre_reprocess_20260417T114500Z.db`
- Reset for full Slack re-extraction:
  - deleted Slack rows from `event_candidates`
  - deleted Slack rows from `events`
  - cleared `event_relations`
  - cleared `llm_calls` cache/history table
- Re-ran `scripts/run_multi_source_pipeline.py --source slack` iteratively until no pending `new` candidates.

## KPI Comparison (Pre vs Post)

Pre DB: `data/slack_events.pre_reprocess_20260417T114500Z.db`
Post DB: `data/slack_events.db`

| Metric | Pre | Post | Delta |
|---|---:|---:|---:|
| events_total | 119 | 41 | -78 |
| event_messages_total | 90 | 41 | -49 |
| pct_multi_event_messages | 21.11% | 0.00% | -21.11 pp |
| pct_future_like | 6.72% | 0.00% | -6.72 pp |
| pct_action_other | 6.72% | 0.00% | -6.72 pp |
| pct_low_utility_summaries | 0.00% | 0.00% | 0 pp |
| pct_low_coverage_summaries | 8.40% | 2.44% | -5.96 pp |

## Operational Snapshot
- raw_messages: 144 (unchanged)
- candidates_total: 105 (unchanged)
- candidates_llm_ok: 105 (unchanged)
- llm_calls: pre 105 → post 102
- llm_cost_usd: pre 0.033389 → post 0.042357
- events_per_candidate: pre 1.133 → post 0.390
- events_per_raw_message: pre 0.826 → post 0.285

## Channel Distribution Check
- Pre events by channel:
  - C04V0TK7UG6: 108
  - C04UCRJ7UTF: 11
- Post events by channel:
  - C04V0TK7UG6: 41
  - C04UCRJ7UTF: 0
- Post candidates by channel:
  - C04V0TK7UG6: 86
  - C04UCRJ7UTF: 19

Observation: channel `C04UCRJ7UTF` still produces candidates but 0 accepted events post-reprocess, indicating potential channel-specific over-filtering.

## Agent Post-Analysis (runSubagent)
1. **observability-telemetry**
   - Confirms strong cleanup in target quality classes.
   - Flags likely over-filtering risk from volume collapse.
   - Recommends adding per-rule reject telemetry and counterfactual sampling.

2. **verification-reviewer**
   - P0: PASS
   - P1: PASS (guarded)
   - P2: PASS (guarded)
   - Overall verdict: **Partial** due to recall risk and missing labeled recall proof.

3. **researcher**
   - Flags probable recall skew by channel (`C04UCRJ7UTF`).
   - Recommends stage-funnel audit and per-rule reject-rate split by channel.

## Recommended Next Iteration
1. Add per-rule reject counters with `channel_id` and `reason_code`.
2. Add channel-sliced extraction funnel report (ingested → candidate → accepted).
3. Introduce balanced summary-contract gate (retain strict gate as audit metric), then rerun sampled backfill and compare.
4. Add release gate thresholds on recall/volume floor to prevent silent over-filtering.

---

## Iteration 2 — Balanced Contract + Telemetry

### Code Changes
- Added balanced contract mode (`require_effect=False`) while keeping strict mode available.
- Added runtime counters:
  - `summary_contract_reject_missing_change`
  - `summary_contract_reject_missing_scope`
  - `summary_contract_soft_accept_missing_effect`
  - `summary_contract_soft_accept_rate`

### Result
- KPI movement from strict baseline backup (`pre_change_recovery`) showed no recall gain at this step:
  - `events_total`: 41 → 41
  - `pct_low_coverage_summaries`: 0.00% → 0.00%
- Runtime counters showed dominant blocker was `missing_change`, not `missing_effect`.

## Iteration 3 — Action-Based Change Recovery

### Code Changes
- Added deterministic `action_implies_change()` policy.
- `summary_contract_components()` now treats canonical change actions as valid change evidence.
- Added telemetry:
  - `summary_contract_change_recovered_from_action`

### KPI Comparison (Pre vs Post)

Pre DB: `data/slack_events.pre_change_recovery_20260417T121618Z.db`
Post DB: `data/slack_events.db`

| Metric | Pre | Post | Delta |
|---|---:|---:|---:|
| events_total | 41 | 85 | +44 |
| event_messages_total | 41 | 85 | +44 |
| pct_multi_event_messages | 0.00% | 0.00% | 0 pp |
| pct_future_like | 0.00% | 0.00% | 0 pp |
| pct_action_other | 0.00% | 0.00% | 0 pp |
| pct_low_coverage_summaries | 0.00% | 1.18% | +1.18 pp |

### Operational Snapshot
- raw_messages: 144 → 144
- candidates_total: 105 → 105
- llm_calls: 102 → 102
- llm_cost_usd: 0.042079 → 0.042461
- events_per_candidate: 0.390 → 0.810
- events_per_raw_message: 0.285 → 0.590

### Agent Post-Analysis (runSubagent)
1. **observability-telemetry**
   - Judgement: strong recall gain at near-flat cost.
   - Risk: `low_coverage` increased to 1.18%, should be guarded.
2. **verification-reviewer**
   - Verdict: **Pass (guarded)**.
   - Recommendation: staged rollout with stop conditions on quality regressions.

## Current Status
- System moved from over-filtered state (`events_total=41`) to balanced state (`events_total=85`) while preserving key P0/P1 protections in this dataset.
- Next control point: keep release gate on `low_coverage` trend and channel-level drift.

## Iteration 4 — Non-Event Override for Strong Change Signals

### Code Changes
- Added strong operational-change signal override before non-event filtering (e.g., delist/disable/remove/rollback in EN/RU stems).
- Kept existing non-event guard for seminar/research/help-only posts.
- Regression tests expanded for RU delist/disable phrasing with help wording.

### Result
- Runtime rescue attempts became non-zero in hard reprocess (`t_product_rescue_attempts=1`), confirming path activation.
- Immediate KPI impact was limited to global volume, not minority-channel lift in that pass.

## Iteration 5 — Focused t-product Rescue Prompt

### Code Changes
- Added `_build_t_product_rescue_text()` in extraction use case to reduce noisy context for second-pass rescue.
- Rescue now focuses on high-signal change lines (delist/disable/remove/rollback etc.) instead of full noisy message body.

### KPI Comparison (Pre vs Post)

Pre DB: `data/slack_events.pre_rescue_focus_20260417T133701Z.db`
Post DB: `data/slack_events.db`

| Metric | Pre | Post | Delta |
|---|---:|---:|---:|
| events_total | 86 | 87 | +1 |
| event_messages_total | 86 | 87 | +1 |
| pct_multi_event_messages | 0.00% | 0.00% | 0 pp |
| pct_future_like | 0.00% | 0.00% | 0 pp |
| pct_action_other | 0.00% | 0.00% | 0 pp |
| pct_low_coverage_summaries | 2.33% | 2.30% | -0.03 pp |

### Channel Recall Delta
- `C04UCRJ7UTF`: **5.26% → 10.53%** (+5.27 pp; events 1 → 2)
- `C04V0TK7UG6`: **98.84% → 98.84%** (flat)

### Status After Iteration 5
- Minority channel recall improved without breaking P0 guardrails in this benchmark.
- Skew remains high; next iteration should target additional high-confidence t-product false negatives while enforcing:
  - `pct_future_like <= 1%`
  - `pct_action_other <= 1%`
  - `pct_multi_event_messages <= 2.5%`
