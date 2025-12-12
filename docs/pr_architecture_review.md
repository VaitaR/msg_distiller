# Architectural Review – Slack Event Manager

## Вехи (хронология)
- **2025‑10‑17** — PostgresRepository + Alembic (#5, #68): нужен production storage, итог — dual‑DB, но появился миграционный долг.
- **2025‑10‑18** — Multi-source + Telegram ingestion (#11, #14): расширили охват, последовали многочисленные фиксы из‑за контрактов.
- **2025‑10‑19** — Репозитории и EventValidator догнаны до протокола (#27, #30, #31, #34): устранили падения и браки.
- **2025‑10‑20** — Полная изоляция источников и Telethon loop management (#37, #39, #40, #41): pipeline перестал останавливаться после ingestion.
- **2025‑10‑23** — Structured logging + dashboard decoupling + candidate leasing (#43‑#47): повысили наблюдаемость и самовосстановление.
- **2025‑10‑24** — SlackStateStore, кеши, job runner, bulk upsert, LLM budgeting (#48‑#53): инфраструктурный апгрейд ради 429‑стойкости и контроля бюджета.
- **2025‑10‑31** — Telegram schema/from_date фиксы (#55, #56): выровняли миграции и историческую выборку.
- **2025‑11‑04** — Connection pool hardening + LLM cache TTL (#57‑#59): сняли ресурсный стресс и почистили кеш.
- **2025‑11‑08** — Postgres task queue, worker services, отдельный metrics exporter (#60‑#64, #67): перешли к worker‑архитектуре.
- **2025‑11‑12** — Slack state нормализация, Alembic cleanup, pool tuning, Telegram config совместимость (#66‑#74, #76): закрытие долгов перед аудитом.

## ADR-карточки

### ADR-001 — Dual Database with Alembic
- **Область**: storage/db; **Тип**: introduce → improve.
- **Контекст**: SQLite не покрывал прод-нагрузку, нужен Postgres с ACID и JSONB (#5).
- **Решение**: PostgresRepository, repository_factory, Alembic миграции, env precedence (#5, #68).
- **Альтернативы**: остаться на SQLite (не тянет), MySQL (нет JSONB) — отвергнуты.
- **Компромиссы**: рост сложности миграций, необходимость держать паритет двух БД.
- **Последствия**: reliability↑, performance↑, cost↑, complexity↑, observability=neutral.
- **Жизненный цикл**: introduced_at #5 → improved_at #68/#55/#66 → replaced_by null.
- **Метрики**: unknown (PR указывает на 100 msgs/19 events прогон).
- **Связанные PRы**: [5, 68, 55, 66].

### ADR-002 — Multi-Source Pipeline & Telegram Integration
- **Область**: domain + data-model + adapters; **Тип**: introduce → improve.
- **Контекст**: требовалась поддержка Telegram + будущих источников (#11, #14).
- **Решение**: MessageSource enum, source_id поля, Telethon client, orchestration скрипт.
- **Альтернативы**: отдельные пайплайны per source — отклонены (дублирование).
- **Компромиссы**: сложные миграции, async/loop управление, множественные state таблицы.
- **Последствия**: reliability↑ (после фиксов), complexity↑, observability↓ (пока не добавили структурные логи), cost↑ (дополнительные вызовы).
- **Жизненный цикл**: introduced_at #11/#14 → improved_at #34/#37/#40/#41/#56/#70/#72/#76 → replaced_by null.
- **Метрики**: Telegram прогон 823 сообщений (#56).
- **Связанные PRы**: [11, 14, 34, 37, 39, 40, 41, 54, 56, 70, 72, 76].

### ADR-003 — Versioned Prompts & Deterministic LLM Caching
- **Область**: llm/agents; **Тип**: introduce → improve.
- **Контекст**: нужно контролировать стоимость/латентность и отслеживать промпты (#20, #25).
- **Решение**: YAML промпты, LLMClient с hashing/caching, TTL (#48, #53, #59).
- **Альтернативы**: inline prompts без кеша — отказались из‑за стоимости.
- **Компромиссы**: управление TTL/инвалидацией, больше конфигов, риск устаревших кешей.
- **Последствия**: cost↓, performance↑, complexity↑, observability↑ (логирование хешей).
- **Жизненный цикл**: introduced_at #20/#25 → improved_at #48/#53/#59.
- **Метрики**: указано снижение LLM вызовов (точное значение unknown).
- **Связанные PRы**: [20, 25, 48, 53, 59, 73, 74].

### ADR-004 — EventValidator Gating
- **Область**: domain/data-quality; **Тип**: improve.
- **Контекст**: LLM сохранял события с критическими нарушениями (#30).
- **Решение**: EventValidator на этапах extract/dedup/publish, блокировка critical (#30, #35).
- **Альтернативы**: ручной QA, warn-only — отвергнуты как ненадёжные.
- **Компромиссы**: возможная потеря части событий, необходимость аудита логов.
- **Последствия**: reliability↑, data quality↑, complexity↑, observability↑ (аудит логов).
- **Жизненный цикл**: introduced_at #30 → improved_at #35.
- **Метрики**: unknown (есть ссылки на 23 теста).
- **Связанные PRы**: [30, 35].

### ADR-005 — Slack State Store, Caching & Job Runner
- **Область**: batch/stream + infra; **Тип**: introduce → improve.
- **Контекст**: Slack 429 и отсутствие централизованных курсоров (#48‑#52).
- **Решение**: SlackStateStore (#49), user/permalink caches + retry/backoff (#50), job runner + auth + metrics (#51).
- **Альтернативы**: продолжать хранить курсоры inline — неустойчиво; сторонние очереди — не потребовались.
- **Компромиссы**: дополнительные таблицы, кеш инвалидация.
- **Последствия**: reliability↑, performance↑ (меньше API), cost↓, complexity↑, observability↑ (Prometheus метрики).
- **Жизненный цикл**: introduced_at #48/#49/#50/#51/#52 → improved_at #66 (state normalization).
- **Метрики**: unknown (фактические значения не приведены).
- **Связанные PRы**: [48, 49, 50, 51, 52, 66].

### ADR-006 — Postgres Task Queue & Workerization
- **Область**: queues/streaming + infra/IaC; **Тип**: introduce → scale.
- **Контекст**: монолитный pipeline стал узким местом (#60).
- **Решение**: task queue таблицы, воркеры (ingest/extraction/LLM/dedup), runtime helpers, отдельный metrics exporter (#60‑#64, #67).
- **Альтернативы**: сторонний брокер (Celery/Kafka) — не выбран (лишняя зависимость).
- **Компромиссы**: Postgres как SPOF, необходимость тюнинга пула (#69).
- **Последствия**: scalability↑, reliability↑ (разделение задач), complexity↑, cost↑ (больше сервисов), observability↑.
- **Жизненный цикл**: introduced_at #60 → improved_at #61/#62/#63/#64/#67/#69.
- **Метрики**: unknown.
- **Связанные PRы**: [60, 61, 62, 63, 64, 67, 69].

### ADR-007 — Structured Logging & Metrics Expansion
- **Область**: observability; **Тип**: introduce → improve.
- **Контекст**: нужны машинно-читаемые логи, таймауты в CI (#43, #44).
- **Решение**: structlog, Prometheus exporter auto-start (#63/#67), Pytest timeout (#44).
- **Альтернативы**: оставаться на print/logging basic — отвергнуто из‑за отсутствия контекста.
- **Компромиссы**: зависимость от structlog, необходимость настройки metrics service.
- **Последствия**: observability↑, complexity↑ (отдельный сервис), cost↑ (доп. контейнер).
- **Жизненный цикл**: introduced_at #43/#44 → improved_at #63/#67.
- **Метрики**: audit план упоминает проверку `/metrics` (значения unknown).
- **Связанные PRы**: [43, 44, 63, 67].

## Матрица судьбы технологий

| technology | area | status | intro_pr | last_change_pr | reason_for_change | impact_axes | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PostgresRepository + Alembic | storage/db | improved | 5 | 66 | Миграции расходились между БД (#55/#66) | reliability↑ performance↑ cost↑ complexity↑ observability=neutral | Dual-DB режим требует постоянных миграций |
| Multi-source pipeline (source_id + Telethon) | domain/data-model | improved | 11 | 76 | Контрактный дрейф и конфигурации Telegram (#34/#37/#56/#72) | reliability↑ (после фиксов) performance=neutral cost↑ complexity↑ observability↓ | Требует строгого конфиг-моста |
| YAML prompts + LLM cache | llm/agents | improved | 20 | 74 | TTL/ORDER BY ошибки (#59/#73) | cost↓ performance↑ complexity↑ observability↑ | TTL добавлен, SQLite update исправлен |
| EventValidator gate | domain | kept | 30 | 35 | Нужны критические блокировки | reliability↑ complexity↑ | Стал стабильным контрактом |
| SlackStateStore + caches | batch/stream | improved | 48 | 66 | Термины таблиц расходились (#66) | reliability↑ performance↑ complexity↑ observability↑ | Автоматическая миграция legacy таблиц |
| Postgres task queue workers | queues/streaming | improved | 60 | 69 | Pool exhaustion (#57→#69) | scalability↑ reliability↑ cost↑ complexity↑ observability↑ | Требует тюнинга пула |
| Structlog + Prometheus exporter | observability | improved | 43 | 67 | Нужно выносить metrics в отдельный сервис (#67) | observability↑ cost↑ complexity↑ | Экспортер стал отдельным контейнером |
| Telegram config reader (Mapping/Pydantic) | config | improved | 11 | 76 | Смешанные типы ломали скрипты (#70/#72/#76) | reliability↑ complexity↑ devex↓ | Повторные фиксы намекают на необходимость унификации |

## Каталог причин изменений
- **Несоответствие нагрузке/SLI**: Postgres pool exhaustion (#57 → #69); переход на worker queue (#60 → #62).
- **Консистентность/идемпотентность**: candidate leasing и recovery (#46/#47); EventValidator gating (#30/#35).
- **Миграции/схемы**: Slack ingestion state rename (#49, #55, #66); Telegram raw schema fixes (#31, #54, #56).
- **Контракты API/версионирование**: RepositoryProtocol vs Postgres (#18/#22 vs #27); Telegram config objects (#70/#72/#76).
- **CI/CD/скорость релиза**: параллельный CI (#21/#19), `make ci` alias (#42), pytest-timeout (#44).
- **Операционные затраты**: LLM caching (#20/#59), Slack caching (#50).
- **Вендор-лок/совместимость**: Telethon fallback без Telethon (#33/#41); psycopg2 fallback (#33).
- **Наблюдаемость/алерты**: structlog и metrics exporter (#43/#67); audit test plan (#67).
- **Долг после LLM-генерации**: повторные фиксы config/parsers (#45, #56, #70, #72, #76) и Protocol drift (#27/#34).

## Что сработало хорошо
- **EventValidator как стабильный контракт** (#30, #35): после внедрения не потребовалось замен, снижены ошибки качества данных.
- **Slack caching & backoff** (#50, #66): кеш + state store снижали 429 и сохранились через несколько фаз без отката.
- **LLM prompt versioning** (#20, #48, #53, #59): архитектура кеша развивалась эволюционно (добавили TTL, фиксы SQLite) без полной замены.
- **Structured logging** (#43, #44, #67): после внедрения лишь улучшали (Prometheus exporter), лог формат остался неизменным — повысило наблюдаемость.

## Что пришлось усиливать/заменять
- **RepositoryProtocol ↔ Postgres** (#18/#22 → #27): изначально интерфейсы не совпадали, пришлось добавлять query_* и тесты; компромисс — необходимость контрактных тестов.
- **Telegram ingestion конфиги** (#11 → #56 → #70/#72/#76): смешение dict/Pydantic привело к множественным фиксам; требуется унификация модели.
- **Multi-source pipeline orchestration** (#11 → #37/#40): ранняя версия прерывала Telegram поток после ingestion; добавили source isolation и полный проход.
- **Postgres pool** (#57 → #69): агрессивные minconn настроены слишком высоко, пришлось снижать и документировать тюнинг.
- **LLM cache persistor** (#48 → #73): SQLite UPDATE с ORDER BY ломал запись кеша; потребовался рефактор и предупреждения.

## Рекомендации (если собирать заново)
1. **Контрактные тесты RepoProtocol (R‑01)** → потому что эпизоды #18/#22/#27; эффект: предотвращение drift; гварды: dual-backend CI, schema snapshots.
2. **Единый формат message_sources (R‑02)** → эпизоды #56/#70/#72/#76; эффект: меньше конфиг‑фиксов; гварды: JSON Schema + миграция.
3. **Automated Alembic vs SQLite diff (R‑03)** → эпизоды #49/#55/#66; эффект: нет колонок-привидений; гварды: миграционный тест.
4. **E2E pipeline тест для каждого source (R‑04)** → эпизоды #37/#40; эффект: гарантированный полный цикл; гварды: synthetic fixtures.
5. **Pool/queue SLO + алерты (R‑05)** → эпизоды #57/#69, #60‑#62; эффект: ранний сигнал о resource exhaustion; гварды: Prometheus rules.
6. **Prompt/cache change checklist (R‑06)** → эпизоды #20/#59/#73; эффект: нет stale cache; гварды: hash+TTL tests.
7. **Observable config loader (R‑07)** → эпизоды #45/#56; эффект: логируемые конфиг миграции; гварды: audit hook.
8. **Async client harness (R‑08)** → эпизоды #33/#41; эффект: устранить loop хаос; гварды: integration test с реальным event loop.

## JSON артефакт
```json
{
  "decisions": [
    {
      "id": "ADR-001",
      "title": "Dual Database with Alembic",
      "area": "storage/db",
      "context": "SQLite не тянул продовую нагрузку и требовалась Postgres совместимость (#5).",
      "decision": {"tech": "PostgreSQL + Alembic", "pattern": ["repository_factory", "env precedence"]},
      "alternatives": ["SQLite only", "MySQL"],
      "tradeoffs": ["ops_cost_up", "complexity_up"],
      "consequences": {"reliability": "up", "performance": "up", "cost": "up", "complexity": "up", "observability": "neutral"},
      "lifecycle": {"introduced_pr": 5, "improved_prs": [68, 55, 66], "replaced_by": null, "removed_pr": null},
      "metrics": {"messages_processed": 100, "events": 19},
      "related_prs": [5, 68, 55, 66]
    },
    {
      "id": "ADR-002",
      "title": "Multi-source Pipeline & Telegram Integration",
      "area": "domain",
      "context": "Нужно подключить Telegram и будущие источники (#11, #14).",
      "decision": {"tech": "MessageSource + Telethon", "pattern": ["source isolation", "per-source config"]},
      "alternatives": ["Separate pipelines"],
      "tradeoffs": ["complexity_up", "async_management"],
      "consequences": {"reliability": "up_after_fixes", "performance": "neutral", "cost": "up", "complexity": "up", "observability": "down_until_structlog"},
      "lifecycle": {"introduced_pr": 11, "improved_prs": [34, 37, 40, 41, 56, 70, 72, 76], "replaced_by": null, "removed_pr": null},
      "metrics": {"telegram_messages": 823},
      "related_prs": [11, 14, 34, 37, 39, 40, 41, 54, 56, 70, 72, 76]
    },
    {
      "id": "ADR-003",
      "title": "Versioned Prompts & Deterministic LLM Cache",
      "area": "llm/agents",
      "context": "Нужно снизить стоимость LLM и контролировать промпты (#20, #25).",
      "decision": {"tech": "YAML prompts + cache + TTL", "pattern": ["prompt hashing", "response caching"]},
      "alternatives": ["Inline prompts"],
      "tradeoffs": ["config_sprawl", "cache_invalidation"],
      "consequences": {"cost": "down", "performance": "up", "complexity": "up", "observability": "up"},
      "lifecycle": {"introduced_pr": 20, "improved_prs": [25, 48, 53, 59, 73, 74], "replaced_by": null, "removed_pr": null},
      "metrics": {"llm_cache_hits": "unknown"},
      "related_prs": [20, 25, 48, 53, 59, 73, 74]
    },
    {
      "id": "ADR-004",
      "title": "EventValidator as Gate",
      "area": "domain",
      "context": "LLM сохранял события с критическими ошибками (#30).",
      "decision": {"tech": "EventValidator service", "pattern": ["multi-stage validation"]},
      "alternatives": ["manual QA", "warnings_only"],
      "tradeoffs": ["potential_event_loss", "runtime_cost"],
      "consequences": {"reliability": "up", "complexity": "up", "observability": "up"},
      "lifecycle": {"introduced_pr": 30, "improved_prs": [35], "replaced_by": null, "removed_pr": null},
      "metrics": {"validation_tests": 23},
      "related_prs": [30, 35]
    },
    {
      "id": "ADR-005",
      "title": "Slack State Store, Caches & Job Runner",
      "area": "batch/stream",
      "context": "Не хватало устойчивости к 429 и централизованных курсоров (#48-#50).",
      "decision": {"tech": "SlackStateStore + caching + job runner", "pattern": ["stateful ingestion", "retry/backoff"]},
      "alternatives": ["Inline cursors"],
      "tradeoffs": ["extra_tables", "cache_management"],
      "consequences": {"reliability": "up", "performance": "up", "cost": "down", "complexity": "up", "observability": "up"},
      "lifecycle": {"introduced_pr": 48, "improved_prs": [49, 50, 51, 52, 66], "replaced_by": null, "removed_pr": null},
      "metrics": {"slack_cache_hits": "unknown"},
      "related_prs": [48, 49, 50, 51, 52, 66]
    },
    {
      "id": "ADR-006",
      "title": "Postgres Task Queue & Workerization",
      "area": "queues/streaming",
      "context": "Монолитный pipeline не масштабировался (#60).",
      "decision": {"tech": "Postgres-backed task queue + worker services", "pattern": ["ingest/extract/LLM/dedup workers"]},
      "alternatives": ["External MQ"],
      "tradeoffs": ["postgres_spof", "pool_tuning"],
      "consequences": {"scalability": "up", "reliability": "up", "cost": "up", "complexity": "up", "observability": "up"},
      "lifecycle": {"introduced_pr": 60, "improved_prs": [61, 62, 63, 64, 67, 69], "replaced_by": null, "removed_pr": null},
      "metrics": {"worker_smoke_tests": "pass"},
      "related_prs": [60, 61, 62, 63, 64, 67, 69]
    },
    {
      "id": "ADR-007",
      "title": "Structured Logging & Metrics Exporter",
      "area": "observability",
      "context": "Нужна трассировка и защита CI от зависаний (#43, #44).",
      "decision": {"tech": "structlog + Prometheus exporter service", "pattern": ["JSON logging", "dedicated exporter"]},
      "alternatives": ["basic logging"],
      "tradeoffs": ["extra_service", "config_overhead"],
      "consequences": {"observability": "up", "cost": "up", "complexity": "up"},
      "lifecycle": {"introduced_pr": 43, "improved_prs": [44, 63, 67], "replaced_by": null, "removed_pr": null},
      "metrics": {"audit_metrics_endpoint": "covered"},
      "related_prs": [43, 44, 63, 67]
    }
  ],
  "technology_matrix": [
    {"technology": "PostgresRepository + Alembic", "area": "storage/db", "status": "improved", "intro_pr": 5, "last_change_pr": 66, "reason_for_change": "schema drift (#55)", "impact_axes": {"reliability": "up", "performance": "up", "cost": "up", "complexity": "up", "devex": "down", "security": "neutral", "observability": "neutral"}, "notes": "Needs dual-schema parity"},
    {"technology": "Multi-source pipeline", "area": "domain", "status": "improved", "intro_pr": 11, "last_change_pr": 76, "reason_for_change": "config/contract fixes (#34/#56/#70)", "impact_axes": {"reliability": "up_after_fixes", "performance": "neutral", "cost": "up", "complexity": "up", "devex": "down", "security": "neutral", "observability": "down_then_up"}, "notes": "Requires consistent config loader"},
    {"technology": "LLM prompt cache", "area": "llm/agents", "status": "improved", "intro_pr": 20, "last_change_pr": 74, "reason_for_change": "TTL/order fixes (#59/#73)", "impact_axes": {"reliability": "up", "performance": "up", "cost": "down", "complexity": "up", "devex": "neutral", "security": "neutral", "observability": "up"}, "notes": "TTL enforced, SQLite update fixed"},
    {"technology": "EventValidator", "area": "domain", "status": "kept", "intro_pr": 30, "last_change_pr": 35, "reason_for_change": "None", "impact_axes": {"reliability": "up", "performance": "down_minor", "cost": "neutral", "complexity": "up", "devex": "neutral", "security": "neutral", "observability": "up"}, "notes": "Stable contract"},
    {"technology": "SlackStateStore & caches", "area": "batch/stream", "status": "improved", "intro_pr": 48, "last_change_pr": 66, "reason_for_change": "table rename/migration (#66)", "impact_axes": {"reliability": "up", "performance": "up", "cost": "down", "complexity": "up", "devex": "down", "security": "neutral", "observability": "up"}, "notes": "Legacy table view added"},
    {"technology": "Postgres task queue workers", "area": "queues/streaming", "status": "improved", "intro_pr": 60, "last_change_pr": 69, "reason_for_change": "pool exhaustion (#57/#69)", "impact_axes": {"reliability": "up", "performance": "up", "cost": "up", "complexity": "up", "devex": "down", "security": "neutral", "observability": "up"}, "notes": "Requires pool monitoring"},
    {"technology": "Structlog + metrics exporter", "area": "observability", "status": "improved", "intro_pr": 43, "last_change_pr": 67, "reason_for_change": "Need dedicated exporter (#67)", "impact_axes": {"reliability": "neutral", "performance": "neutral", "cost": "up", "complexity": "up", "devex": "neutral", "security": "neutral", "observability": "up"}, "notes": "Exporter container introduced"},
    {"technology": "Telegram config reader", "area": "config", "status": "improved", "intro_pr": 11, "last_change_pr": 76, "reason_for_change": "Mapping vs Pydantic mismatches (#70/#72/#76)", "impact_axes": {"reliability": "up", "performance": "neutral", "cost": "neutral", "complexity": "up", "devex": "down", "security": "neutral", "observability": "neutral"}, "notes": "Still brittle without unified schema"}
  ],
  "reasons_catalog": [
    {"reason": "load_sli_mismatch", "episodes": [57, 69, 60]},
    {"reason": "consistency_idempotency", "episodes": [46, 47, 30]},
    {"reason": "schema_migrations", "episodes": [49, 55, 66, 31, 54, 56]},
    {"reason": "api_contract_drift", "episodes": [18, 22, 27, 34, 70, 72, 76]},
    {"reason": "ci_speed", "episodes": [21, 42, 44]},
    {"reason": "operational_cost", "episodes": [20, 50, 59]},
    {"reason": "vendor_compatibility", "episodes": [33, 41]},
    {"reason": "observability_alerts", "episodes": [43, 67]},
    {"reason": "llm_generated_debt", "episodes": [45, 56, 70, 72, 76]}
  ],
  "worked_well": ["ADR-003", "ADR-004", "ADR-005", "ADR-007"],
  "needed_changes": ["ADR-001", "ADR-002", "ADR-006"],
  "recommendations": [
    {"ref": "R-01", "summary": "Ввести контрактные тесты для RepositoryProtocol на SQLite+Postgres", "because_of": ["episodes:18,22,27", "reason:api_contract_drift"], "expected_effect": "Zero drift for adapters", "guards": ["CI dual-backend suite", "schema snapshots"]},
    {"ref": "R-02", "summary": "Унифицировать формат message_sources и валидировать через JSON Schema", "because_of": ["episodes:56,70,72,76", "reason:llm_generated_debt"], "expected_effect": "Fewer Telegram config regressions", "guards": ["schema validation", "migration script tests"]},
    {"ref": "R-03", "summary": "Добавить автоматический diff Alembic vs SQLite", "because_of": ["episodes:49,55,66", "reason:schema_migrations"], "expected_effect": "No missing columns", "guards": ["migration golden tests"]},
    {"ref": "R-04", "summary": "CI e2e прогон для каждого источника (Slack/Telegram)", "because_of": ["episodes:37,40", "reason:consistency_idempotency"], "expected_effect": "Pipeline stages always executed", "guards": ["fixture data", "stage assertions"]},
    {"ref": "R-05", "summary": "SLO и алерты на pool usage и worker queue depth", "because_of": ["episodes:57,69,60", "reason:load_sli_mismatch"], "expected_effect": "Early warning on resource exhaustion", "guards": ["Prometheus alerts"]},
    {"ref": "R-06", "summary": "Checklist для LLM prompt/cache изменений", "because_of": ["episodes:20,59,73"], "expected_effect": "Predictable cache invalidation", "guards": ["hash verification", "TTL tests"]},
    {"ref": "R-07", "summary": "Наблюдаемый config loader с логированием миграций", "because_of": ["episodes:45,56"], "expected_effect": "Traceable config auto-migrations", "guards": ["structlog fields", "dry-run mode"]},
    {"ref": "R-08", "summary": "Async client harness и health tests для Telethon", "because_of": ["episodes:33,41"], "expected_effect": "No event-loop regressions", "guards": ["async integration tests"]}
  ]
}
```
