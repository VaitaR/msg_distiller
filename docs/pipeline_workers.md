# Pipeline Workers

This document describes the queue-based runtime.

## Services

| Service | Purpose | Default command |
| --- | --- | --- |
| `pipeline-scheduler` | Enqueue periodic pipeline iterations | `python scripts/run_pipeline_scheduler.py --interval-seconds 300` |
| `ingest-worker` | Process ingestion tasks and build candidates | `python scripts/run_ingest_worker.py` |
| `extraction-worker` | Schedule LLM extraction tasks from candidate queue | `python scripts/run_extraction_worker.py` |
| `llm-worker` | Execute per-candidate LLM extraction | `python scripts/run_llm_worker.py` |
| `dedup-worker` | Deduplicate extracted events | `python scripts/run_dedup_worker.py` |

## Important Runtime Note

Current queue ingestion composition (`create_slack_ingestion_handlers`) is Slack-oriented.
For complete multi-source end-to-end processing in a single process, use:

```bash
python scripts/run_multi_source_pipeline.py
```

## Bootstrap / Smoke Test

```bash
python scripts/run_pipeline_scheduler.py --run-once
python scripts/run_ingest_worker.py --run-once
python scripts/run_extraction_worker.py --run-once
python scripts/run_llm_worker.py --run-once
python scripts/run_dedup_worker.py --run-once
```

## Queue Inspection (PostgreSQL)

```bash
docker compose exec postgres psql \
  -U ${POSTGRES_USER:-postgres} \
  -d ${POSTGRES_DATABASE:-slack_events} \
  -c "SELECT task_type, status, COUNT(*)\n      FROM pipeline_tasks\n      GROUP BY task_type, status\n      ORDER BY task_type, status;"
```

## Scaling

Example: scale LLM workers horizontally.

```bash
docker compose up --scale llm-worker=3 -d
```
