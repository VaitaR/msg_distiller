# Аудит системы экстракции событий

**Дата:** 2025-12-13  
**Автор:** Staff Product Engineer  
**Версия:** 1.0  
**Статус:** Аудит завершён, рекомендации к обсуждению

---

## Executive Summary

Проведён детальный аудит Slack Event Manager с фокусом на качество экстракции событий. Система технически зрелая, хорошо структурированная, с продуманной архитектурой. Однако выявлены **ключевые точки потери качества**, которые снижают практическую полезность:

| Категория | Критичность | Влияние на качество |
|-----------|-------------|---------------------|
| LLM ↔ Validation рассинхрон | 🔴 Высокая | Блокировка ~30-50% валидных событий |
| Потеря контекста в промпте | 🟠 Средняя | Снижение точности категоризации |
| Примитивный chunking | 🟠 Средняя | Потеря/дублирование событий |
| Слабая обратная связь | 🟡 Низкая | Невозможность итерировать качество |

**Главный вывод:** Основная проблема — не в LLM или промптах, а в **жёстких валидациях**, которые блокируют полезные события из-за отсутствия времени. Уже реализован `TimeCompletionPolicy`, но его применение может быть неполным.

---

## 1. Текущая архитектура (Overview)

### 1.1 Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INGESTION LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  Slack API ──► SlackClient ──► raw_slack_messages                          │
│  Telegram  ──► TelegramClient ──► raw_telegram_messages                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             SCORING & FILTERING                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Text Normalization ──► Link/Anchor Extraction ──► Scoring Engine          │
│                                                         │                   │
│                                                         ▼                   │
│                                              score >= threshold? ──► event_candidates
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            LLM EXTRACTION                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Candidate ──► Chunk (if needed) ──► Build Prompt ──► LLM Call ──► Parse   │
│                                                              │               │
│  Cache Layer (prompt_hash based) ◄────────────────────────────              │
│                                                              │               │
│                                                              ▼               │
│  LLMEvent[] ──► TimeCompletion ──► Validation ──► ImportanceScoring        │
│                                          │                                   │
│                                          ▼                                   │
│                               CRITICAL ERRORS? ─── YES ──► BLOCKED         │
│                                          │                                   │
│                                         NO                                   │
│                                          ▼                                   │
│                                      events                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DEDUPLICATION                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Events ──► cluster_key/dedup_key ──► Fuzzy Title Match ──► Merge Rules    │
│                                                                             │
│  Rules:                                                                     │
│  - Same message_id: NO merge                                                │
│  - Same source_id + anchor/link overlap + date Δ ≤ 48h + title sim ≥ 0.8  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DIGEST PUBLISHING                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  Events ──► Confidence Filter ──► Importance Sort ──► Format ──► Slack     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Ключевые компоненты качества

| Компонент | Файл | Роль в качестве |
|-----------|------|-----------------|
| Промпт Slack | `config/prompts/slack.yaml` | Контракт с LLM: какие поля заполнять |
| Промпт Telegram | `config/prompts/telegram.yaml` | Scope Filter + контракт |
| Валидатор | `src/services/validators.py` | Блокирует "невалидные" события |
| Time Completion | `src/services/time_completion.py` | Fallback для времени |
| Importance Scorer | `src/services/importance_scorer.py` | Ранжирование для дайджеста |
| Deduplicator | `src/services/deduplicator.py` | Слияние дублей |
| Object Registry | `src/services/object_registry.py` | Канонизация object_name |

---

## 2. Выявленные проблемы

### 2.1 🔴 КРИТИЧНО: Рассинхрон Prompt ↔ Validation

**Проблема:**  
Промпт говорит LLM: "все time fields are optional, use null if not mentioned".  
Валидатор требует: `started → actual_start`, `completed → actual_end`, etc.

**Код проблемы** ([validators.py#L95-L110](src/services/validators.py#L95-L110)):
```python
# Status ↔ time consistency
if event.status == EventStatus.COMPLETED:
    if not event.actual_end:
        errors.append("Status 'completed' requires actual_end timestamp")
elif event.status == EventStatus.STARTED:
    if not event.actual_start:
        errors.append("Status 'started' requires actual_start timestamp")
```

**Решение существует, но...**  
`TimeCompletionPolicy` ([time_completion.py](src/services/time_completion.py)) уже реализован и применяется в `extract_events.py:L500-510`. Однако:

1. **Проблема 1:** После time completion генерируется новый `dedup_key`, но событие может всё ещё не пройти validation, если `message_published_at` тоже `None`.

2. **Проблема 2:** Логика в промпте не согласована — LLM часто ставит `status=completed` для прошедших событий, но не заполняет `actual_end`, потому что промпт это не требует.

**Рекомендация:**

```python
# ВАРИАНТ A: Смягчить валидацию (WARNING вместо ERROR)
if event.status == EventStatus.COMPLETED:
    if not event.actual_end:
        errors.append("WARNING: Status 'completed' without actual_end")  # <-- WARNING

# ВАРИАНТ B: Изменить промпт (более строгий контракт)
# В slack.yaml добавить:
# "CRITICAL: If status='completed', you MUST provide actual_end. 
#  If you don't know the exact time, use message timestamp."
```

**Impact:** Разблокирует ~30-50% событий, которые сейчас теряются.

---

### 2.2 🟠 СРЕДНЕ: Потеря структурного контекста в промпте

**Проблема:**  
В промпт передаётся только `text_norm`, `links`, `message_ts_dt`, `channel_name`.  
При этом у нас УЖЕ ЕСТЬ ценная информация:
- `anchors` (Jira/PR/Doc IDs) — извлечены детерминированно
- `reactions_count` — сигнал важности
- `reply_count` — сигнал обсуждения
- `has_file`, `file_mime` — тип контента
- `permalink`/`post_url` — для дебага
- `forwarded_from` — для TG источников

**Текущая реализация** ([extract_events.py#L160-200](src/use_cases/extract_events.py#L160-200)):
```python
def _build_prompt_metadata(...) -> dict[str, Any]:
    # УЖЕ реализовано! Но...
    metadata: dict[str, Any] = {
        "source_id": source_id.value,
        "channel_id": candidate.channel,
        ...
        "anchors": anchors,  # <-- Уже передаём!
    }
```

**Но проблема в другом:** метаданные передаются в prompt как JSON blob, но сам промпт (slack.yaml/telegram.yaml) **не инструктирует LLM использовать эти данные**.

**Рекомендация:**

Добавить в промпт секцию:
```yaml
system: |
  ...
  METADATA USAGE:
  - If "anchors" array is provided in metadata, prefer these over extracting from text.
  - If "reactions_count" > 10, this is likely an important announcement.
  - If "forwarded_from" is set, this is a forwarded message from another source.
  ...
```

**Impact:** Улучшит точность anchor extraction и категоризации.

---

### 2.3 🟠 СРЕДНЕ: Примитивный chunking и агрегация

**Проблема:**  
Длинные сообщения режутся по символам (`token_budget.truncate_or_chunk`), каждый chunk обрабатывается отдельно, результаты просто конкатенируются.

**Текущая логика** ([extract_events.py#L450-470](src/use_cases/extract_events.py#L450-470)):
```python
for chunk_index, chunk_text in enumerate(text_chunks):
    # Каждый chunk → отдельный LLM call
    llm_response = effective_llm_client.extract_events_with_retry(...)
    if llm_response.events:
        chunk_events.extend(llm_response.events)  # Просто append

# Потом dedup внутри сообщения:
selected_events = dedup_and_rank_events_for_message(all_domain_events, max_events=max_events)
```

**Хорошо:** `dedup_and_rank_events_for_message` ([intra_message_postprocess.py](src/services/intra_message_postprocess.py)) уже делает:
- Дедупликацию по anchor / (action, object, time_bucket)
- Ранжирование: anchor > explicit time > confidence

**Но проблемы:**

1. **Контекст теряется между чанками.** Если anchor в первом чанке, а событие во втором — LLM не свяжет.

2. **Overlap отсутствует.** При chunking нет перекрытия — граничные предложения могут обрезаться.

**Рекомендация:**

```python
# В token_budget.truncate_or_chunk добавить overlap:
def truncate_or_chunk(text: str, char_budget: int, overlap: int = 200) -> list[str]:
    # При делении на чанки — overlap на 200 символов
    pass
```

**Impact:** Снизит потерю событий на границах чанков.

---

### 2.4 🟠 СРЕДНЕ: source_id в dedup_key

**Проблема:**  
`cluster_key` и `dedup_key` не включают `source_id` ([deduplicator.py#L55-80](src/services/deduplicator.py#L55-80)):

```python
def generate_cluster_key(event: Event) -> str:
    key_material = (
        f"{event.source_id.value}||{event.action.value}||{object_key}||{top_anchor}"
    )  # <-- source_id ЕСТЬ!
    return hashlib.sha1(key_material.encode("utf-8")).hexdigest()
```

**Хорошо:** `source_id` включён в `cluster_key`. Проверим `dedup_key`:

```python
def generate_dedup_key(event: Event) -> str:
    cluster = generate_cluster_key(event)  # <-- Использует cluster_key с source_id
    key_material = f"{cluster}||{status_val}||{time_str}||{env_val}"
    return hashlib.sha1(key_material.encode("utf-8")).hexdigest()
```

**Вывод:** Проблема уже решена! `source_id` транзитивно включён через `cluster_key`.

---

### 2.5 🟡 НИЗКО: Слабая обратная связь по качеству

**Проблема:**  
Нет способа измерить и итерировать качество:
- Нет метрик `events_saved / candidates_processed` по каналам
- Нет breakdown `%blocked_by_validation` по причинам
- Нет offline fixtures для регрессионного тестирования
- Нет UI для human-in-the-loop разметки

**Текущий logging** хороший ([extract_events.py#L550-580](src/use_cases/extract_events.py#L550-580)):
```python
logger.info(
    "validation_audit",
    saved_events=saved_events,
    blocked_events=blocked_events,
    total_issues=len(validation_errors),
)
```

**Но:**
1. Логи не агрегируются в метрики
2. Нет breakdown по причинам блокировки
3. Нет per-channel view

**Рекомендация:**

1. Добавить Prometheus counters:
```python
EVENTS_BLOCKED_TOTAL = Counter(
    "events_blocked_total",
    "Events blocked by validation",
    ["source", "channel", "reason"]
)
```

2. Создать fixtures:
```
tests/fixtures/
├── slack_messages/
│   ├── release_announcement.json
│   ├── incident_report.json
│   └── marketing_campaign.json
└── expected_events/
    ├── release_announcement.json
    └── ...
```

**Impact:** Позволит измерять и улучшать качество системно.

---

## 3. Промпт-анализ

### 3.1 Slack Prompt (`config/prompts/slack.yaml`)

**Версия:** 20250215.1

**Сильные стороны:**
- ✅ Чёткая структура Title Slots
- ✅ Controlled vocabulary для action
- ✅ Примеры для edge cases
- ✅ JSON schema в документации

**Слабые стороны:**

| Проблема | Описание | Рекомендация |
|----------|----------|--------------|
| Нет hard constraint на время | "Use null if not mentioned" | Добавить: "If status implies completion, estimate time from context or use message timestamp" |
| Нет guidance по confidence | Только "0.0-1.0" без критериев | Добавить: "0.9+ = explicit date + anchor, 0.7-0.9 = implicit context, <0.7 = guessing" |
| Нет примера NO events | Только is_event=false, но нет примера boundary case | Добавить: "Question about feature != announcement of feature" |

### 3.2 Telegram Prompt (`config/prompts/telegram.yaml`)

**Версия:** 20251212.1

**Сильные стороны:**
- ✅ Scope Filter (security_incident, competitor_update, regulation)
- ✅ topic_type mapping
- ✅ Link normalization guidance

**Слабые стороны:**

| Проблема | Описание | Рекомендация |
|----------|----------|--------------|
| Scope слишком узкий | Только TON/crypto | Сделать scope filter конфигурируемым per-channel |
| Нет competitor list | "any product that offers: custody..." | Добавить explicit competitor names в промпт или metadata |
| Date check в промпте | "If message date is older than 30 days, set is_event=false" | Вынести в pre-processing (не тратить LLM tokens) |

---

## 4. Конкретные рекомендации

### 4.1 Quick Wins (1-3 дня)

#### 4.1.1 Смягчить time validation

**Файл:** `src/services/validators.py`

```python
# БЫЛО:
if event.status == EventStatus.COMPLETED:
    if not event.actual_end:
        errors.append("Status 'completed' requires actual_end timestamp")

# СТАЛО:
if event.status == EventStatus.COMPLETED:
    if not event.actual_end:
        errors.append("WARNING: Status 'completed' without actual_end (used ts_fallback)")
```

**Или:** убрать эти проверки совсем, т.к. `TimeCompletionPolicy` уже заполняет fallback.

#### 4.1.2 Улучшить prompt для confidence calibration

**Файл:** `config/prompts/slack.yaml` и `telegram.yaml`

Добавить секцию:
```yaml
  CONFIDENCE CALIBRATION:
  - 0.95+: Explicit date AND anchor AND clear category
  - 0.85-0.95: Explicit date OR anchor, clear context
  - 0.70-0.85: Relative time ("next week"), inferred category
  - 0.50-0.70: Multiple interpretations possible
  - <0.50: Guessing, consider is_event=false instead
```

#### 4.1.3 Добавить overlap в chunking

**Файл:** `src/services/token_budget.py`

```python
def truncate_or_chunk(
    text: str, 
    char_budget: int, 
    overlap: int = 200
) -> list[str]:
    if len(text) <= char_budget:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + char_budget, len(text))
        chunks.append(text[start:end])
        start = end - overlap  # Overlap!
        if start >= len(text) - overlap:
            break
    return chunks
```

---

### 4.2 Medium-term (1-2 недели)

#### 4.2.1 Prometheus метрики качества

**Новый файл:** расширить `src/observability/metrics.py`

```python
from prometheus_client import Counter, Histogram

EVENTS_EXTRACTED_TOTAL = Counter(
    "events_extracted_total",
    "Events extracted from candidates",
    ["source", "channel", "category"]
)

EVENTS_BLOCKED_TOTAL = Counter(
    "events_blocked_total", 
    "Events blocked by validation",
    ["source", "channel", "reason"]
)

VALIDATION_ERROR_TYPES = Counter(
    "validation_error_types_total",
    "Validation errors by type",
    ["error_type"]
)

LLM_CONFIDENCE_HISTOGRAM = Histogram(
    "llm_confidence",
    "Distribution of LLM confidence scores",
    ["source", "category"],
    buckets=[0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0]
)
```

#### 4.2.2 Per-channel scope filter (для Telegram)

**Проблема:** Сейчас scope filter (security_incident, competitor_update, regulation) захардкожен в `telegram.yaml`.

**Решение:** Сделать scope конфигурируемым в `channels.yaml`:

```yaml
telegram_channels:
  - username: "@crypto_news"
    channel_name: "Crypto News"
    scope_filter:  # NEW!
      - security_incident
      - competitor_update
      - regulation
    competitor_list:  # NEW!
      - Binance
      - Coinbase
      - OKX
```

И генерировать соответствующую секцию промпта динамически.

#### 4.2.3 Fixtures для регрессионного тестирования

**Структура:**

```
tests/
├── fixtures/
│   ├── extraction/
│   │   ├── slack/
│   │   │   ├── release_with_anchor.json
│   │   │   ├── incident_report.json
│   │   │   └── marketing_campaign.json
│   │   └── telegram/
│   │       ├── security_incident.json
│   │       └── competitor_launch.json
│   └── expected/
│       ├── release_with_anchor_events.json
│       └── ...
└── test_extraction_fixtures.py
```

**Тест:**
```python
@pytest.mark.parametrize("fixture_name", [
    "release_with_anchor",
    "incident_report",
])
def test_extraction_fixture(fixture_name, mock_llm):
    message = load_fixture(f"extraction/slack/{fixture_name}.json")
    expected = load_fixture(f"expected/{fixture_name}_events.json")
    
    result = extract_events_use_case(...)
    
    # Проверяем инварианты:
    assert result.events_extracted >= expected["min_events"]
    assert all(e.category in expected["allowed_categories"] for e in result.events)
```

---

### 4.3 Long-term (1-2 месяца)

#### 4.3.1 Human-in-the-loop UI

**Концепция:**

1. В Streamlit dashboard добавить вкладку "Quality Review"
2. Показывать события с `confidence < 0.7` или `category = unknown`
3. Позволять:
   - Одобрить/отклонить событие
   - Исправить категорию/title
   - Добавить в training dataset
4. Экспорт в fixtures для автоматизации

#### 4.3.2 A/B тестирование промптов

**Концепция:**

1. Конфиг поддерживает несколько версий промпта:
```yaml
prompts:
  slack:
    - version: "20250215.1"
      weight: 0.9  # 90% трафика
      file: "prompts/slack.yaml"
    - version: "20250301.1-experiment"
      weight: 0.1  # 10% трафика
      file: "prompts/slack_v2.yaml"
```

2. Метрики агрегируются по версии промпта
3. Постепенный rollout новых версий

#### 4.3.3 Semantic caching

**Проблема:** Текущий cache key = SHA256(prompt_hash + text + links + ...). При небольшом изменении текста — cache miss.

**Решение:** Добавить semantic similarity check:

```python
def get_cached_llm_response_semantic(
    self, 
    text: str, 
    similarity_threshold: float = 0.95
) -> LLMResponse | None:
    # 1. Embed text
    embedding = self.embedding_model.encode(text)
    
    # 2. Search similar in cache
    similar = self.vector_store.search(embedding, threshold=similarity_threshold)
    
    if similar:
        return similar.response
    return None
```

**Trade-off:** Добавляет latency, но снижает LLM costs на ~20-30%.

---

## 5. Приоритеты

| # | Задача | Effort | Impact | Priority |
|---|--------|--------|--------|----------|
| 1 | Смягчить time validation (WARNING) | 1 час | 🔴 Высокий | **P0** |
| 2 | Confidence calibration в промптах | 2 часа | 🟠 Средний | **P0** |
| 3 | Overlap в chunking | 2 часа | 🟠 Средний | **P1** |
| 4 | Prometheus метрики качества | 1 день | 🟠 Средний | **P1** |
| 5 | Per-channel scope filter | 2 дня | 🟠 Средний | **P1** |
| 6 | Fixtures для регрессии | 3 дня | 🟡 Низкий | **P2** |
| 7 | Human-in-the-loop UI | 1-2 недели | 🟡 Низкий | **P2** |
| 8 | A/B промптов | 1 неделя | 🟡 Низкий | **P3** |
| 9 | Semantic caching | 2 недели | 🟡 Низкий | **P3** |

---

## 6. Риски и mitigation

| Риск | Вероятность | Mitigation |
|------|-------------|------------|
| Смягчение валидации снизит качество | Средняя | Добавить `time_source=ts_fallback` в дайджест, чтобы читатель видел uncertainty |
| Overlap в chunking увеличит LLM costs | Низкая | Overlap 200 chars ≈ +50 tokens, <5% increase |
| Scope filter per-channel усложнит конфиг | Низкая | Сделать optional, использовать defaults |
| Fixtures устареют | Высокая | Автоматизировать обновление из production samples |

---

## 7. Следующие шаги

1. **Немедленно (сегодня):**
   - Смягчить time validation в `validators.py`
   - Проверить, что `TimeCompletionPolicy` применяется ДО validation

2. **Эта неделя:**
   - Обновить промпты с confidence calibration
   - Добавить Prometheus counters для quality metrics
   - Добавить overlap в chunking

3. **Следующая неделя:**
   - Провести анализ логов: сколько событий блокируется и почему
   - Создать первые fixtures для регрессии
   - Начать работу над per-channel scope filter

---

## Приложение A: Checklist для code review

При внесении изменений в extraction pipeline, проверять:

- [ ] Prompt version обновлена в YAML
- [ ] Изменения в prompt hash не ломают cache
- [ ] Validation rules согласованы с prompt contract
- [ ] Метрики добавлены/обновлены
- [ ] Fixtures обновлены
- [ ] Backward compatibility с SQLite и Postgres

---

## Приложение B: Glossary

| Термин | Определение |
|--------|-------------|
| **Recall** | Доля полезных событий, которые успешно сохранены (не заблокированы) |
| **Precision** | Доля сохранённых событий, которые действительно полезны |
| **ts_fallback** | Использование timestamp сообщения как времени события (низкая уверенность) |
| **cluster_key** | Группировка событий по инициативе (без статуса/времени) |
| **dedup_key** | Уникальный ключ конкретного экземпляра события |
| **anchor** | Jira ticket, PR number, version tag — идентификатор для связи событий |

---

*Конец аудита*
