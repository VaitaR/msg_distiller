# Техническое задание: улучшение качества экстракции событий (Slack + Telegram)

**Проект:** Slack Event Manager  
**Статус:** Draft  
**Версия:** 0.1  
**Последнее обновление:** 2025-12-13  
**Автор:** Codex (staff product engineer)  

## 1) Контекст и проблема

Сервис решает проблему хаоса и низкой наблюдаемости в корпоративных Slack‑каналах и новостных/конкурентных Telegram‑каналах: важные сигналы теряются в шуме. Пайплайн извлекает из сообщений структурированные события (event stream), нормализует их, присваивает метаданные (категория, важность, время, источник), дедуплицирует и публикует дайджест.

Текущий болевой эффект: **низкий выход валидных событий (recall)** при реальных данных. Основная причина — **рассинхрон между контрактом, который просим у LLM, и валидациями**, из‑за чего события часто блокируются как “невалидные”, даже если они полезны.

Цель этого ТЗ — описать изменения, которые:
- увеличат долю сохранённых/публикуемых событий при сохранении качества,
- улучшат точность времени/статуса и стабильность дедупликации,
- позволят тонко настраивать экстракцию по каналам,
- добавят измеримость качества (метрики/алерты) и облегчат итерации.

## 2) Термины

- **Raw message** — сырой Slack/TG payload, сохранённый в БД (`raw_slack_messages`, `raw_telegram_messages`).
- **Candidate** — сообщение, прошедшее скоринг и поставленное на LLM‑экстракцию (`event_candidates`).
- **Event** — структурированное событие (`events`), источник истины для дайджеста и аналитики.
- **time_source** — источник времени (`explicit|relative|ts_fallback`).
- **message_published_at** — timestamp исходного сообщения (UTC), используется как “якорь” для `ts_fallback`.
- **cluster_key / dedup_key** — ключи для группировки и дедупликации (см. `src/services/deduplicator.py`).

## 3) Текущее устройство (важные ссылки в коде)

**Пайплайн (в общих чертах):**
1) Ingest → 2) Normalize/Extract links+anchors → 3) Score → 4) Build candidates → 5) LLM extract → 6) Validate → 7) Save → 8) Deduplicate → 9) Publish digest

**Ключевые модули:**
- Ingest Slack: `src/use_cases/ingest_messages.py`
- Ingest Telegram: `src/use_cases/ingest_telegram_messages.py`
- Candidate scoring: `src/services/scoring_engine.py`
- Link/anchor extraction: `src/services/link_extractor.py`
- Text normalization: `src/services/text_normalizer.py`
- LLM client + prompt loading: `src/adapters/llm_client.py`, `config/prompts/*.yaml`
- LLM extraction orchestration + caching: `src/use_cases/extract_events.py`
- Validation: `src/services/validators.py`
- Deduplication: `src/services/deduplicator.py`, `src/use_cases/deduplicate_events.py`
- Repositories: `src/adapters/sqlite_repository.py`, `src/adapters/postgres_repository.py`
- Observability: `src/config/logging_config.py`, `src/observability/metrics.py`, `docs/OPERATIONS_OBSERVABILITY.md`

## 4) Диагноз: основные причины потери качества/recall

### 4.1 Рассинхрон LLM ↔ Validation (time/status)

Промпт разрешает `planned_start/actual_start/actual_end = null`, но валидатор делает эти поля **обязательными** по статусу:
- `started` требует `actual_start`
- `completed` требует `actual_end`
- `planned|confirmed` требуют `planned_start`

Фактически это часто блокирует реальные события (особенно TG‑новости), где время не указано явно.

### 4.2 Потеря структурного контекста до LLM

До LLM у нас уже есть сигналы высокого качества (anchors, reactions, replies, has_file, permalink/post_url, forwarded_from), но в prompt обычно уходит только `text_norm` + links + timestamp. LLM “не видит” ключевые подсказки, которые могли бы повысить точность/стабильность.

### 4.3 Нет per‑channel prompt routing

Конфиг поддерживает `prompt_file` на уровне `ChannelConfig`/`TelegramChannelConfig`, но в реальном запуске LLM‑клиент создаётся per‑source. Нельзя быстро улучшать качество на конкретном канале (например, `#releases` vs `#incidents` vs `@crypto_news`) без влияния на всё.

### 4.4 Chunking и агрегация результатов

При больших сообщениях текст режется по символам, результаты из чанков просто конкатенируются и потом обрезаются до `llm_max_events_per_msg`. Это:
- даёт дубли между чанками,
- теряет приоритет событий (ранний чанк может вытеснить более важный поздний),
- усложняет повторяемость и кэширование.

### 4.5 Ключи дедупликации и `source_id`

Дедупликация запрещает слияние событий между источниками, но `cluster_key/dedup_key` не включают `source_id`, а `dedup_key` уникален в БД. Теоретически возможны коллизии “одинаковых” событий из Slack и TG.

## 5) Цели и метрики успеха

### 5.1 Цели
- **Повысить recall** (сохранённых событий) без деградации качества дайджеста.
- Сделать time/status устойчивыми: “время не указано” не должно убивать событие.
- Включить per‑channel промпты и быстрые итерации.
- Сделать качество измеримым в проде (метрики/алерты) и в офлайне (фикстуры).

### 5.2 KPI (минимальный набор)

Онлайн (prod):
- `events_saved / candidates_processed` (по source/channel)
- `%blocked_by_validation` (по причине, source/channel)
- `unknown_category_rate`
- `llm_cache_hit_rate`
- `cost_usd / saved_event`
- `p50/p95 llm_latency_ms`

Офлайн (на фикстурах):
- доля событий с `time_source != ts_fallback`
- стабильность key’ей (dedup_key) при повторном прогоне
- доля событий с anchors

## 6) Предлагаемые изменения (план работ)

Ниже — рекомендуемая разбивка на фазы. Фаза P0 — обязательна, P1 — очень желательна, P2 — стратегическая.

### P0 — “Разблокировать recall” (1–3 дня)

#### P0.1 TimeCompletionPolicy (post-processing времени)

**Идея:** если LLM не дал обязательное время, мы должны корректно заполнить его из `message_published_at` и явно маркировать как `ts_fallback` с низкой уверенностью.

**Правила заполнения (если целевое поле пустое):**
- `planned|confirmed` → `planned_start = message_published_at`
- `started` → `actual_start = message_published_at`
- `completed` → `actual_end = message_published_at`
- Для остальных статусов — не заполняем (если нет явных требований).

**Также:**
- если время заполнено fallback’ом, устанавливаем `time_source=ts_fallback` и `time_confidence = min(time_confidence, 0.3)` (или фиксированно `0.2`).
- если `message_published_at` отсутствует — используем `candidate.ts_dt` (как сейчас).

**Изменения в коде (ориентир):**
- Новый сервис: `src/services/time_completion.py` (или аналогичный модуль)
- Вызов из `src/use_cases/extract_events.py` перед `EventValidator.get_critical_errors()`
- Добавить warning‑лог `time_completed_from_message_ts`

**Acceptance criteria:**
- События со статусом `started/completed/planned/confirmed` больше не блокируются только из‑за отсутствия времени, если есть `message_published_at`.
- Добавлен тест, который покрывает каждый статус и проверяет `time_source/time_confidence`.

#### P0.2 Передача структурного контекста в LLM prompt

**Идея:** дополняем user prompt блоком метаданных, собранных детерминированно (без LLM):
- `source_id`, `channel_id`, `channel_name`
- `message_id`, `message_published_at`, `permalink`/`post_url`
- `anchors` (из `link_extractor.extract_all_anchors`)
- `reactions_count`, `reply_count`, `has_file`, `file_mime`
- `forwarded_from` (для TG)

**Требования к кэшированию:**
если метаданные участвуют в prompt, они должны участвовать и в `_compute_prompt_hash` (иначе кэш может вернуть ответ для другого контекста).

**Изменения в коде (ориентир):**
- Расширить контракт: либо добавить `context: dict[str, Any]` в `LLMClient.extract_events[_with_retry]`, либо новый метод `extract_events_with_context`.
- Обновить `src/domain/protocols.py:LLMClientProtocol` (если используется как тип).
- Обновить `_compute_prompt_hash` в `src/use_cases/extract_events.py`.

**Acceptance criteria:**
- В prompt присутствует “Message metadata” блок (покрыть unit‑тестом на `_build_prompt`/hashing).
- Кэш разделяет ответы для сообщений с разными anchors/metadata при одинаковом `text_norm`.

### P1 — “Управляемое качество” (1–2 недели)

#### P1.1 Per-channel prompt routing

**Идея:** выбирать prompt по каналу (если в конфиге задан `prompt_file`), иначе — по source default.

**Дизайн:**
- Ввести `PromptRouter/LLMClientPool`: кэш `prompt_file -> LLMClient`, чтобы не создавать клиента на каждый candidate.
- В `extract_events_use_case` выбирать клиента для candidate на основе `settings.get_scoring_config(...).prompt_file`.

**Acceptance criteria:**
- Можно задать prompt для одного канала без влияния на остальные.
- Prompt version/hash логируется, кэш по prompt_hash работает корректно.

#### P1.2 Intra-message dedup/ranking при chunking

**Идея:** после получения `chunk_events` выполнить:
1) дедуп событий внутри одного сообщения (по anchor, либо по `(action, object_id/object_name_raw, time_bucket)`),
2) ранжирование (anchor>explicit time>confidence>time_confidence),
3) только потом применять `llm_max_events_per_msg`.

**Acceptance criteria:**
- При длинных сообщениях события из “поздних” чанков не теряются из‑за простого обрезания.
- Дубли внутри одного сообщения исчезают (unit‑тест).

#### P1.3 Дедуп-ключи с учётом `source_id`

**Идея:** включить `source_id` в material для `cluster_key/dedup_key`.

**Миграция:**
- Для SQLite можно пересчитать на чтении/пересохранении или отдельным скриптом.
- Для Postgres — Alembic миграция + backfill.

**Acceptance criteria:**
- Коллизии dedup_key между источниками невозможны по конструкции.

#### P1.4 Репозиторий Postgres: parity для digest filtering

Сейчас `publish_digest_use_case` использует `repository.get_events_in_window_filtered`, который реализован в SQLite и объявлен в `RepositoryProtocol`, но отсутствует в PostgresRepository.

**Acceptance criteria:**
- PostgresRepository реализует `get_events_in_window_filtered` с теми же семантиками COALESCE (учёт `message_published_at`).

### P2 — “Петля качества и продуктовая скорость” (1–2 месяца)

#### P2.1 Офлайн-оценка качества (fixtures + регрессии)

**Идея:** добавить набор anonymized fixtures сообщений и ожидаемых “инвариантов”:
- извлекается ли событие вообще,
- категория/тип,
- наличие anchors,
- корректная стратегия времени.

Цель — мерить изменения промпта/кода как A/B по метрикам, не полагаясь на “ощущения”.

#### P2.2 Human-in-the-loop в UI

**Идея:** интерфейс для разметки “правильно/неправильно”, ручной правки полей, и экспортом в датасет для обучения/промпт‑итераций.

## 7) Нефункциональные требования

- **Безопасность:** не логировать raw prompt/response по умолчанию (сохраняем текущую политику redaction в `src/adapters/llm_client.py`).
- **Стоимость:** сохранить текущий бюджет/кэширование; любое увеличение prompt должно быть в пределах `token_budget.prompt_budget_for_model()`.
- **Совместимость:** не ломать dual‑DB (SQLite/Postgres) и multi-source.
- **Наблюдаемость:** новые метрики и логи должны быть стабильны по имени/лейблам.

## 8) План тестирования

Минимум:
- Unit: `TimeCompletionPolicy`, prompt building + hashing, intra-message dedup.
- Integration: прогон `extract_events_use_case` с mock LLM (события без времени) → событие сохраняется и валидируется.
- Repository parity: Postgres реализация `get_events_in_window_filtered` (если Postgres тесты включаются в окружении).

Рекомендуемо:
- E2E: fixture Slack + fixture Telegram через 4 стадии (ingest→candidates→extract→dedup) с проверкой метрик.

## 9) План внедрения (rollout)

- Флаги (config): включить P0.1/P0.2 через настройки (например, `extraction.time_completion_enabled`, `extraction.prompt_metadata_enabled`).
- Выкатка:
  1) включить в staging, собрать метрики `%blocked_by_validation` и `events_saved/candidate`
  2) включить в prod на части каналов (canary)
  3) расширить на все каналы, зафиксировать baseline метрик

## 10) Риски и вопросы

- Как трактовать “время события” для TG‑новостей: timestamp поста часто “время публикации новости”, а не “время события”. Нужна договорённость, но fallback улучшает полезность.
- Рост prompt может снизить cache hit rate (если включать много уникальных полей) — нужно строго ограничить контекст (anchors/сигналы/ссылки) и не включать полный raw payload.
- Валидации: какие ошибки должны быть “blocking”, а какие — warning (особенно time/status).

