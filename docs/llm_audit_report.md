# Audit Report
- Набор данных: 76 PRов (2025‑10‑11…2025‑11‑12) вытянуты через `gh pr list`; единственный открытый PR #75 (CLI alias for real-data test).
- Дубликаты/эпизоды: PR #4 заменён на #5 (PostgreSQL), #19 закрыт в пользу #21 (параллельный CI), #12 и #20 закрыты без merge; остальные эпизоды слиты по времени merge.
- Тип/область (feat/fix/refactor/docs/build/ci/data/migration × domain/use-case/adapter/infra/observability/security/data-model):  
  E1 (#5 #7 #8 #9 #10) feat/migration infra+data-model; E2 (#11 #14 #20 #25) feat use-case+adapter; E3 (#27‑37) fix adapter+use-case; E4 (#43‑47) fix observability+use-case; E5 (#48‑53) feat/migration infra+llm; E6 (#54‑56) fix data-model; E7 (#57‑59) fix infra; E8 (#60‑64) feat infra/workerization; E9 (#66‑76) fix infra+config.

## Timeline
- **2025‑10‑17** — PostgresRepository, репозитории‑фабрики и новый event schema с англоязычными инвариантами (#5 #7 #8 #9 #10). Почему: нужен production‑grade Postgres без отказа от SQLite. Эффект: готовность к продакшн, риск — двоичное сопровождение схем.
- **2025‑10‑18** — Мульти‑source архитектура, Telegram ingestion и версионированные промпты/кеши (#11 #14 #20 #25). Почему: расширение охвата каналов. Эффект: гибкость, риск — рост сложности и неверная изоляция источников.
- **2025‑10‑19** — Серия хотфиксов: Postgres добирает query_* API, EventValidator блокирует брак, Telegram получает недостающие поля и async совместимость (#27 #29 #30 #31 #32 #33 #34 #35 #36). Почему: выявленные краши после E2. Эффект: стабилизация, риск — churn и техдолг.
- **2025‑10‑20** — Полная изоляция источников и переписанный TelegramClient с управлением loop (#37 #39 #40 #41). Почему: pipeline завершался после ingestion и ловил event-loop deadlock. Эффект: надёжность, риск — усложнение async‑стека.
- **2025‑10‑23** — Дашборд вынесен в query‑use‑cases, включены structlog/pytest-timeout, добавлены lease‑tracking и registry fallback (#43 #44 #45 #46 #47). Почему: наблюдаемость и stuck‑кандидаты. Эффект: лучшее мониторинг+recovery, риск — новые миграции.
- **2025‑10‑24** — Фазы A1‑C2: SlackStateStore, кеши пользователей, job‑runner с auth, bulk upsert, детерминированный LLM budgeting (#48‑#53). Почему: устойчивость к 429 и контроль стоимости LLM. Эффект: зрелая платформа, риск — разросшееся состояние и сложность.
- **2025‑10‑29/31** — Починка Telegram/Postgres схем: placeholders, state‑таблицы, from_date конфиг (#54 #55 #56). Почему: реальные падения на mismatch колонок и игнорирование исторических окон. Эффект: корректные бэкупы, риск — синхронизация миграций вручную.
- **2025‑11‑04** — Усиление connection pooling и TTL для LLM кеша (#57 #58 #59). Почему: exhaustion + устаревшие ответы. Эффект: устойчивость, риск — нужно постоянно тюнить лимиты.
- **2025‑11‑08** — Postgres task queue, LLM workers и отдельный metrics exporter (#60‑#64). Почему: масштабирование pipeline. Эффект: воркеры и наблюдаемость, риск — очередь как SPOF.
- **2025‑11‑12** — Завершение нормализации: Slack state миграции, Prometheus‑служба, Alembic бэкофы, pool floor↓ и серия фиксов Telegram config‑объектов (#66‑#74 #76). Почему: закрытие долгов перед аудитом. Эффект: чистая схема и конфиги, риск — множественные мелкие патчи указывают на дизайн‑пробел.

## ADR-подобный реестр (выдержки)
- **ADR‑001** (#5 #68 #55 #66): dual‑DB c Alembic; альтернатива — SQLite only; компромисс — синхронные схемы; последствия — постоянные фиксы миграций.
- **ADR‑002** (#11 #14 #40 #41 #37): мульти‑source + Telethon; альтернатива — отдельные пайплайны; компромисс — сложные миграции; последствия — цепочка фиксов.
- **ADR‑003** (#20 #25 #48 #53 #59): YAML промпты + кеш/TTL; альтернатива — inline промпты; компромисс — управление TTL; последствия — необходимость TTL enforcement.
- **ADR‑004** (#30 #35): EventValidator как gate; альтернатива — ручной QA; компромисс — возможная потеря эвентов; последствия — лучшее качество, больше логирования.
- **ADR‑005** (#48‑#52): SlackStateStore, кеши, job runner; альтернатива — ad-hoc cursors; компромисс — миграционный долг; последствия — устойчивые 429, но больше state.
- **ADR‑006** (#60‑#64 #67 #69): Postgres queue + воркеры; альтернатива — монолит; компромисс — очередь‑SPOF; последствия — требуется pool/metrics тюнинг.

## Карта проблем → фиксов
- **P‑01**: Postgres dedup падал из-за отсутствующих query_* (#5 → #27). Категория: контракт API. Валидация: новые Postgres тесты. Риск: нет контракт-тестов.
- **P‑02**: Telegram ingestion был привязан к SQLite (#11 → #34). Категория: контракт/ответственность. Валидация: 294 теста. Риск: отсутствует автоматическая проверка паритета.
- **P‑03**: Telegram pipeline завершался после ingestion (#11 → #37). Категория: требования. Валидация: регресс-тест полного потока. Риск: новые источники могут повторить сценарий.
- **P‑04**: Потеря Telegram полей и NameError (#14 → #31). Категория: данные/миграции. Риск: новые поля потребуют строгих чек-листов.
- **P‑05**: Slack ingestion не находил колонку в Postgres (#49 → #55). Категория: миграции. Риск: расхождение SQLite views vs Alembic.
- **P‑06**: `from_date` игнорировался (#11 → #56). Категория: конфигурации. Риск: смешанные типы конфигов по-прежнему требуют патчей (#70/#72/#76).
- **P‑07**: Pool exhaustion из-за minconn=20 (#57 → #69). Категория: производительность. Риск: нет алертов на pool.

## LLM-паттерны
- **interface_drift** — (#18 #22 #27 #34): протоколы менялись без синхронных адаптеров.
- **config_object_churn** — (#45 #56 #70 #72 #76): повторные фиксы обработки TelegramChannelConfig.
- **validation_afterthought** — (#30 #35 #37): доменные проверки добавлялись постфактум.

## Рекомендации
1. Контрактные тесты RepositoryProtocol для SQLite/Postgres (см. P‑01/P‑02).
2. Версионированный schema registry + fuzz-тесты для message_sources (см. P‑06, 2025‑11‑12).
3. Автодифф схем Alembic vs SQLite (ADR‑001, P‑05).
4. CI e2e для Slack+Telegram с проверкой всех стадий (P‑02/P‑03).
5. Метрики и алерты на queue/lease TTL (PR #46/#47, ADR‑006).
6. SLO на DB pool usage + дашборды (P‑07, workerization 2025‑11‑08).
7. Чеклист для промпт/LLM кеш изменений (ADR‑003, 2025‑10‑24).
8. ADR-референсы в PR шаблоне для системных изменений (ADR‑005/006).
- Метрики churn/lead time/TTR/flakiness/reverts: **unknown** (нет данных в PRах).

## JSON артефакт
```json
{
  "timeline": [
    {"date": "2025-10-17", "prs": [5, 7, 8, 9, 10], "summary": "PostgreSQL backend, English-only event model, and config reorg prepared the system for production while keeping SQLite fallback.", "impact": ["data-model", "infra"], "risks": ["dual-schema drift", "migration overhead"]},
    {"date": "2025-10-18", "prs": [11, 14, 20, 25], "summary": "Multi-source architecture plus Telegram ingestion and versioned LLM prompts expanded coverage at the cost of extra complexity.", "impact": ["use-case", "adapter"], "risks": ["source isolation regressions"]},
    {"date": "2025-10-19", "prs": [27, 30, 31, 32, 33, 34, 35, 36], "summary": "Hotfix wave aligned repositories with protocols, enforced validation gates, and prevented Telegram data loss.", "impact": ["stability", "data-quality"], "risks": ["sustained churn"]},
    {"date": "2025-10-20", "prs": [37, 39, 40, 41], "summary": "Source isolation fixes and Telegram client refactors removed early exits and async deadlocks.", "impact": ["reliability", "multisource"], "risks": ["async stack complexity"]},
    {"date": "2025-10-23", "prs": [43, 44, 45, 46, 47], "summary": "Dashboard decoupling, structlog, registry fallback, and lease recovery improved observability and candidate hygiene.", "impact": ["observability", "concurrency"], "risks": ["extra migrations"]},
    {"date": "2025-10-24", "prs": [48, 49, 50, 51, 52, 53], "summary": "Slack ingestion phases delivered caching, state stores, bulk persistence, and deterministic LLM budgeting.", "impact": ["infra", "llm-cost"], "risks": ["state footprint", "cache invalidation"]},
    {"date": "2025-10-29", "prs": [54, 55, 56], "summary": "Telegram/PostgreSQL schema corrections fixed placeholder mismatches and honored from_date configs.", "impact": ["data-model", "config"], "risks": ["manual migration coordination"]},
    {"date": "2025-11-04", "prs": [57, 58, 59], "summary": "Connection pooling was hardened, deprecated channel config removed, and TTL enforcement added to the LLM cache.", "impact": ["performance", "llm-runtime"], "risks": ["pool tuning variance"]},
    {"date": "2025-11-08", "prs": [60, 61, 62, 63, 64], "summary": "Postgres-backed task queue, worker services, and metrics exporter turned the pipeline into orchestrated workers.", "impact": ["scalability", "ops"], "risks": ["queue as SPOF", "operational overhead"]},
    {"date": "2025-11-12", "prs": [66, 67, 68, 69, 70, 71, 72, 73, 74, 76], "summary": "Slack state normalization, dedicated metrics service, Alembic cleanup, pool tuning, and Telegram config fixes closed infra debt.", "impact": ["infra", "config"], "risks": ["config/API churn"]}
  ],
  "decisions": [
    {"id": "ADR-001", "title": "Dual database with Alembic", "context": "Need production-grade PostgreSQL while retaining developer-friendly SQLite flows (#5).", "decision": "Introduce PostgresRepository, repository_factory, and Alembic migrations with env precedence safeguards (#68).", "alternatives": ["Keep SQLite-only deployments", "Rely on ad-hoc SQL scripts"], "tradeoffs": ["Must keep schemas in lockstep", "Higher migration complexity"], "consequences": ["Enables Docker/Postgres, but required follow-up schema fixes (#55, #66).", "Adds ongoing Alembic maintenance burden."], "related_prs": [5, 68, 55, 66]},
    {"id": "ADR-002", "title": "Multi-source pipeline & Telegram integration", "context": "Product needed Slack + Telegram ingestion with shared orchestration (#11, #14).", "decision": "Add MessageSource abstractions, per-source tables, Telethon client, and orchestrator with strict source_id filtering (#40).", "alternatives": ["Duplicate pipelines per source", "Treat Telegram as Slack clone"], "tradeoffs": ["Complex migrations, async handling, state tracking per source"], "consequences": ["Unlocked Telegram ingestion but triggered multiple fixes (#37, #41) when invariants drifted."], "related_prs": [11, 14, 40, 41, 37]},
    {"id": "ADR-003", "title": "Versioned prompts & deterministic LLM caching", "context": "LLM costs/latency rising with unpredictable prompts.", "decision": "Store prompts in versioned YAML, hash prompts/chunks, cache responses with TTL (#20, #25, #48, #53, #59).", "alternatives": ["Inline prompts without caching", "Stateless prompt loading"], "tradeoffs": ["More config assets, need cache invalidation policy"], "consequences": ["Reduced repeated LLM spend but required TTL enforcement when cache grew stale (#59)."], "related_prs": [20, 25, 48, 53, 59]},
    {"id": "ADR-004", "title": "EventValidator gating", "context": "LLM outputs violating domain rules were being persisted (#30).", "decision": "Run EventValidator post-extraction, post-dedup, pre-publish and block critical errors (#30, #35).", "alternatives": ["Manual QA", "Warn-only validation"], "tradeoffs": ["Potentially fewer published events", "Need richer logging"], "consequences": ["Data quality improved; failures surface earlier but require operator response.", "Adds runtime cost to every stage."], "related_prs": [30, 35]},
    {"id": "ADR-005", "title": "Slack ingestion state & caching phases", "context": "Slack rate limits and missing ingestion cursors caused inconsistency (#48-#50).", "decision": "Create SlackStateStore, user/permalink caches, job runner UI with auth and observability (#49-#52).", "alternatives": ["Continue with ad-hoc cursors", "Rely solely on Slack API rate limits"], "tradeoffs": ["Extra tables/migrations, cache invalidation work"], "consequences": ["Better resilience against 429s but more schema debt to maintain.", "UI orchestration requires auth token provisioning."], "related_prs": [48, 49, 50, 51, 52]},
    {"id": "ADR-006", "title": "Postgres task queue & workerization", "context": "Monolithic pipeline could not scale or recover fast (#60).", "decision": "Add task queue domain models, Postgres adapter, dedicated workers and metrics exporter (#60-#64, #67).", "alternatives": ["Single-process scheduler", "External MQ"], "tradeoffs": ["Postgres becomes queue SPOF", "Need ops maturity"], "consequences": ["Enables scaling ingestion/LLM workloads but demands pool tuning (#69) and new monitoring."], "related_prs": [60, 61, 62, 63, 64, 67, 69]}
  ],
  "problems": [
    {"problem_id": "P-01", "symptom": "Postgres deployments crashed during deduplication (missing query_events/query_candidates).", "affected": ["src/adapters/postgres_repository.py", "src/use_cases/deduplicate_events.py"], "root_cause": "contract API/схемы", "introduced_by_pr": 5, "fixed_by_pr": 27, "validation": ["Added Postgres query tests", "Dedup use case verified end-to-end"], "residual_risk": "Future protocol changes may again skip Postgres until contract tests exist."},
    {"problem_id": "P-02", "symptom": "Telegram ingestion only worked with SQLite despite RepositoryProtocol claims.", "affected": ["src/use_cases/ingest_telegram_messages.py", "src/adapters/postgres_repository.py"], "root_cause": "контракт API/схемы", "introduced_by_pr": 11, "fixed_by_pr": 34, "validation": ["294 tests (40 skipped) green across both DBs"], "residual_risk": "Parity relies on manual vigilance; no automated dual-backend suite."},
    {"problem_id": "P-03", "symptom": "Telegram pipeline stopped after ingestion; no candidates/events created.", "affected": ["scripts/run_multi_source_pipeline.py", "use_cases pipeline chain"], "root_cause": "требования/границы ответственности", "introduced_by_pr": 11, "fixed_by_pr": 37, "validation": ["Regression test covering 4-stage Telegram flow"], "residual_risk": "New sources may bypass downstream stages without central orchestration tests."},
    {"problem_id": "P-04", "symptom": "Telegram runtime NameError and lost reply/reaction/post_url fields.", "affected": ["src/domain/models.TelegramMessage", "database schema"], "root_cause": "миграции/данные", "introduced_by_pr": 14, "fixed_by_pr": 31, "validation": ["All 294 tests pass; migrations updated both DBs"], "residual_risk": "Future schema fields risk similar omissions without migration checklists."},
    {"problem_id": "P-05", "symptom": "Slack ingestion failed on Postgres (`last_processed_ts` column missing).", "affected": ["slack_ingestion_state tables", "alembic migrations"], "root_cause": "миграции/данные", "introduced_by_pr": 49, "fixed_by_pr": 55, "validation": ["Slack & Telegram pipelines rerun successfully", "Alembic rename applied"], "residual_risk": "Manual schema edits still risk divergence between SQLite views and Postgres tables."},
    {"problem_id": "P-06", "symptom": "`from_date` in telegram_channels.yaml ignored; only 1-day backfill executed.", "affected": ["src/config/settings.py", "src/use_cases/ingest_telegram_messages.py"], "root_cause": "конфигурации/секреты", "introduced_by_pr": 11, "fixed_by_pr": 56, "validation": ["SQL checks confirmed historical range per channel", "New strategy logs"], "residual_risk": "Multiple config shapes (mapping vs Pydantic) still demand follow-up patches (#70/#72/#76)."},
    {"problem_id": "P-07", "symptom": "Worker pool exhausted DB connections (min 20 per worker).", "affected": ["Postgres connection pool defaults", "docs"], "root_cause": "производительность", "introduced_by_pr": 57, "fixed_by_pr": 69, "validation": ["Lint/typecheck/test suite rerun with new defaults"], "residual_risk": "No runtime alerting yet; mis-tuned pools can recur silently."}
  ],
  "llm_patterns": [
    {"pattern": "interface_drift", "evidence_prs": [18, 22, 27, 34], "notes": "LLM-generated protocol updates landed without synchronized adapter changes, forcing multiple follow-up fixes to restore Postgres parity."},
    {"pattern": "config_object_churn", "evidence_prs": [45, 56, 70, 72, 76], "notes": "Repeated patches were needed to support both dict and TelegramChannelConfig objects, showing lack of holistic config handling when code was initially generated."},
    {"pattern": "validation_afterthought", "evidence_prs": [30, 35, 37], "notes": "Quality gates and stage orchestration were added only after LLM-driven features violated invariants, indicating insufficient upfront test coverage."}
  ],
  "recommendations": [
    {"ref": "R-01", "summary": "Add automated RepositoryProtocol contract tests that run against SQLite and Postgres adapters.", "because_of": ["P-01", "P-02"], "expected_effect": "Prevents interface drift before merge and keeps both backends production-ready."},
    {"ref": "R-02", "summary": "Introduce versioned config schemas plus fuzz tests for dict↔Pydantic coercion of message sources.", "because_of": ["P-06", "timeline:2025-11-12"], "expected_effect": "Eliminates repeated Telegram config hotfixes and ensures from_date/backfill policies load uniformly."},
    {"ref": "R-03", "summary": "Automate SQLite vs Postgres schema diffing (golden dump) as part of Alembic CI.", "because_of": ["P-05", "ADR-001"], "expected_effect": "Flags column-name drift like #55/#66 before deployment."},
    {"ref": "R-04", "summary": "Create CI e2e suite that ingests fixture Slack & Telegram data through all four stages.", "because_of": ["P-02", "P-03"], "expected_effect": "Guarantees source isolation and prevents early-return regressions."},
    {"ref": "R-05", "summary": "Instrument queue depth, lease TTLs, and stuck candidates with alerts tied to Prometheus exporter.", "because_of": ["timeline:2025-10-23", "ADR-006"], "expected_effect": "Surfacing stalled tasks before manual recovery is needed."},
    {"ref": "R-06", "summary": "Define operational SLOs for DB pool usage and expose dashboards from the dedicated metrics service.", "because_of": ["P-07", "timeline:2025-11-08"], "expected_effect": "Prevents silent connection exhaustion after worker scaling changes."},
    {"ref": "R-07", "summary": "Adopt a prompt-change checklist (hash, TTL, budget) and attach it to PR template for LLM-affecting changes.", "because_of": ["ADR-003", "timeline:2025-10-24"], "expected_effect": "Keeps LLM caching predictable and reduces cost regressions."},
    {"ref": "R-08", "summary": "Require lightweight ADR references in PR descriptions for system-level shifts (state stores, workerization).", "because_of": ["ADR-005", "ADR-006"], "expected_effect": "Improves traceability and reduces reliance on long PR descriptions for context."}
  ]
}
```
