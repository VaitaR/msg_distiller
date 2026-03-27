# REF-001 — Спецификация рефакторинга (JTBD + архитектура)

Дата: 2026-03-27  
Статус: Draft v1 (живой документ)

## 1) Контекст и цель

Текущий проект — mature multi-source pipeline (Slack + Telegram) для извлечения событий и публикации дайджестов.  
Целевая эволюция: сделать **data app для внутренних событий компании** с возможностью:

- удобного ревью и исправления событий человеком;
- повторного использования события как структурного слоя для AI-агентов и людей;
- визуализации на timeline;
- поэтапной миграции UI с legacy Streamlit на Dash + Plotly;
- усиления архитектуры под LLM coding agents (поддержка, расширяемость, безопасный рефакторинг).

Ограничения:

- проект зрелый, не greenfield;
- pipeline нельзя ломать (no big-bang);
- AutoFactory bootstrap skill не применять; использовать attach/workflow подход.

---

## 2) JTBD (Product Owner)

### Functional jobs

1. Когда pipeline извлёк события, оператор хочет быстро подтвердить/отклонить/исправить их, чтобы в «истину» попадали только валидные события.  
2. Когда аналитик исследует динамику, он хочет timeline с фильтрами по источнику/категории/дате/статусу.  
3. Когда AI-агент строит отчёт, он хочет стабильный структурированный API/слой событий.

### Emotional jobs

- «Я доверяю данным и понимаю, кто/когда изменил событие».
- «Я контролирую качество, а не “пассивно принимаю LLM output”».

### Social jobs

- «Команда использует единый источник правды по событиям».
- «Руководство принимает решения на подтверждённых событиях, а не на пересказах».

### Ключевые персоны

- Аналитик (timeline/паттерны).
- Ops/PM (review/edit/approve).
- Руководитель (consumption/decision support).
- AI-агент (машинное потребление published events).

---

## 3) Главные проблемы текущего состояния (аудит)

1. Монолитный UI-файл Streamlit (сложно поддерживать/мигрировать).
2. Сильная связность repository-слоя (god-interface).
3. Нет backend API-слоя для UI и AI-потребителей.
4. Слабая декомпозиция lifecycle событий для human review.
5. Очередной runtime частично Slack-ориентирован.
6. Не хватает явного audit trail human edits.
7. Недостаточная наблюдаемость (trace-level).
8. Неполный контур e2e UI-тестирования.

---

## 4) Целевая архитектура

Стиль: **Modular Monolith + Ports & Adapters**, усиленный API-слоем.

### Bounded contexts

1. Ingestion (raw messages, source state)
2. Extraction (candidate -> event -> dedup)
3. Event Review & Publication (новый)
4. Presentation (Dash UI + API)

### Модульные границы

- `src/domain`: модели, enum, контракты (без I/O).
- `src/use_cases`: orchestration use cases.
- `src/adapters`: DB/clients/LLM реализации.
- `src/api` (новый): FastAPI endpoints для events/timeline/review.
- `src/presentation/dash` (новый): Dash UI; только HTTP к API.
- `src/presentation/streamlit` (legacy): временно до cutover.

---

## 5) Слой событий (event layer) и lifecycle

Разделить:

- доменный статус события (planned/started/completed);
- статус обработки pipeline (new/processing/ok/error);
- **новый review lifecycle**.

### Новый review lifecycle

`raw -> candidate -> extracted -> deduplicated -> needs_review -> approved -> published -> archived` (+ `rejected`).

### Новые сущности/поля

- `review_status` (`needs_review|approved|published|rejected|archived`)
- `reviewed_by`, `reviewed_at`
- `version`, `origin` (`ai_extraction|human_edit|system_merge`)
- `event_audit_log` (append-only)
- `event_versions` (история версий события)

---

## 6) Продуктовые требования (MVP)

1. Review Queue: фильтры, сортировки, approve/reject/edit.
2. Timeline UX: Plotly timeline + drill-down карточка события.
3. Редактирование полей события с diff-preview.
4. Audit trail всех изменений.
5. Published events как канонический слой для людей и AI.

Non-goals (итерация 1):

- сложный RBAC/многоступенчатые согласования;
- real-time co-editing;
- полная перепаковка pipeline.

---

## 7) Технологический baseline

Приоритетный стек:

- Python 3.12 (3.13 в CI matrix позже)
- uv
- ruff
- pytest
- structlog
- justfile
- docker/docker-compose
- pre-commit
- ty (параллельно с mypy)
- .editorconfig
- OpenTelemetry
- pydantic-settings
- Dash + Plotly
- FastAPI (API-слой)

---

## 8) Критерии готовности (Definition of Done)

1. Pipeline работает без регрессий.
2. Dash UI закрывает сценарии review + timeline.
3. Streamlit удалён после достижения feature parity.
4. Все изменения событий пишутся в audit trail.
5. Есть API для программного доступа к published events.
6. Есть e2e UI тесты (Playwright) и интеграционные API тесты.
7. Архитектурные границы зафиксированы в документации.

---

## 9) Метрики успеха

- Median review time/event
- Время extracted -> published
- Доля событий с human review
- Доля rejected/edited (сигнал качества extraction)
- p95 API latency
- Test coverage core modules
- Кол-во регрессий по pipeline после релизов

---

## 10) Режим работы по AutoFactory (attach/workflow)

- Работать через change-packages и итеративные планы.
- Не делать bootstrap/force rewrite репозитория.
- Для каждой фазы: spec -> implementation -> checks -> review.
- Фиксировать `allowed_paths` и границы ответственности изменений.

---

## 11) Назначенные специализированные агентные роли

1. **Audit Agent** — инвентаризация слабых мест, рисков и техдолга.
2. **Architecture Agent** — проектирование целевой модульной архитектуры.
3. **Product Owner Agent (JTBD)** — jobs, сценарии, приоритеты, метрики.
4. **Refactor Agent** — поэтапная декомпозиция/миграция модулей.
5. **UI Agent (Dash/Plotly)** — UX и фронт-компоненты.
6. **QA/Test Agent (Playwright)** — e2e сценарии и quality gates.

Документ обновляется по ходу работ.
