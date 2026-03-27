# PLAN-001 — Master Plan рефакторинга (задачи и подзадачи)

Дата старта: 2026-03-27  
Статус: Active (дополняемый)

Связанный документ: REF-001_refactor_spec_jtbd_architecture.md

## 0) Управление планом

- Формат: фазы -> задачи -> подзадачи -> артефакты -> DoD.
- Обновление: после каждой завершённой задачи.
- Принцип: маленькие безопасные изменения без остановки текущего pipeline.

---

## Фаза A — Аудит и архитектурное закрепление

### A1. Архитектурный аудит (завершено)
- [x] Карта слоёв и проблемных зон.
- [x] Риски миграции Streamlit -> Dash.
- [x] Выявление ограничений для LLM-agent-friendly кода.

Артефакт:
- Спецификация REF-001.

### A2. Целевая архитектура (завершено)
- [x] Выбор стиля: Modular Monolith + Ports/Adapters + API layer.
- [x] Определение bounded contexts.
- [x] Фиксация модульных границ.

### A3. JTBD/PO слой (завершено)
- [x] Functional/emotional/social jobs.
- [x] Персоны и сценарии.
- [x] MVP/non-goals.

---

## Фаза B — Foundation (инфраструктура изменений)

### B1. Quality baseline
- [ ] Добавить `.editorconfig`.
- [ ] Ввести `justfile` (с сохранением совместимости с Makefile).
- [ ] Расширить pre-commit хуки (ruff/pytest/type checks).
- [ ] Подготовить `ty` в экспериментальном CI job.

### B2. Python runtime alignment
- [ ] Зафиксировать Python 3.12 как основной target.
- [ ] Добавить 3.13 в CI matrix (non-blocking сначала).

### B3. Test governance
- [ ] Обновить тестовую пирамиду (unit/integration/e2e).
- [ ] Ввести coverage gate для core.
- [ ] Подготовить baseline API contract tests.

---

## Фаза C — Event Review Layer (backend-first)

### C1. Domain model evolution
- [ ] Добавить review lifecycle enum и связанные поля.
- [ ] Определить `EventAuditEntry`/`EventVersion` модели.

### C2. Database migration
- [ ] Alembic migration для `review_status`, `reviewed_by`, `reviewed_at`, `version`, `origin`.
- [ ] Таблицы `event_audit_log`, `event_versions`.
- [ ] Backfill для существующих events.

### C3. Repository split/refactor
- [ ] Выделить под-интерфейсы вместо god-interface.
- [ ] Добавить методы review/edit/publish.
- [ ] Сохранить обратную совместимость на переходный период.

### C4. Use cases
- [ ] Новый use case `review_events`.
- [ ] Правила auto-publish по confidence threshold.
- [ ] Audit trail на каждое изменение.

---

## Фаза D — API слой и миграция UI

### D1. API server
- [ ] Создать `src/api` (FastAPI).
- [ ] Endpoints: list/get events, timeline, review actions, health/stats.
- [ ] OpenAPI + pydantic schemas.

### D2. Dash app (side-by-side)
- [ ] Создать `src/presentation/dash`.
- [ ] Реализовать review queue экран.
- [ ] Реализовать timeline экран на Plotly.
- [ ] Подключить только через API (без прямого repo доступа).

### D3. Cutover strategy
- [ ] Проверить feature parity Streamlit vs Dash.
- [ ] Переключить основной UI на Dash.
- [ ] Удалить legacy Streamlit-код и зависимость.

---

## Фаза E — Тестирование и наблюдаемость

### E1. Playwright e2e
- [ ] Инициализировать Playwright сценарии для Dash UI.
- [ ] Покрыть critical flows: login/access, review, edit, timeline filters.
- [ ] Встроить e2e запуск в CI отдельным job.

### E2. Observability
- [ ] Внедрить OpenTelemetry для API/use-cases/workers.
- [ ] Добавить dashboard/алерты по latency/errors/review backlog.
- [ ] Коррелировать логи pipeline + UI actions.

---

## Фаза F — Оптимизация под LLM coding agents

### F1. Снижение когнитивной сложности
- [ ] Дробление крупных модулей на small cohesive units.
- [ ] Явные контракты/DTO между слоями.
- [ ] Стандартизировать шаблоны тестов/фикстур.

### F2. Repo ergonomics
- [ ] Упорядочить `scripts/` (prod/dev/ops).
- [ ] Документировать architecture decision records (ADR).
- [ ] Добавить карту модулей и dependency rules.

---

## План специализироанных агентов по этапам

1. **Audit Agent** — A/B ревизии и risk tracking.
2. **Architecture Agent** — C/D границы и ADR.
3. **PO JTBD Agent** — приоритизация backlog и acceptance criteria.
4. **Refactor Agent** — C1-C4 реализация малыми PR-порциями.
5. **UI Agent (Dash)** — D2/D3 UX flows.
6. **QA Agent (Playwright)** — E1 + regression matrix.
7. **Observability Agent** — E2.

---

## Acceptance на ближайший спринт (Sprint 1) — ✅ DONE

- [x] B1.1 `.editorconfig` — обновлён (добавлены toml, justfile, Dockerfile секции)
- [x] B1.2 `justfile` — создан с полным набором рецептов (sync, fmt, lint, test, api, dash, ci, docker)
- [x] B2 Python 3.12 target — pyproject.toml, ruff, mypy обновлены
- [x] C1.1 Review lifecycle в domain — `ReviewLifecycleStatus`, `EventOrigin`, `EventAuditEntry`, `EventVersion`
- [x] C2.1 Alembic migration — `202603271800_add_event_review_lifecycle.py`
- [x] C2.2 SQLite schema — review columns + audit/versions tables + indexes
- [x] C3 Repository methods — 10 новых методов в SQLiteRepository
- [x] C4 Use case — `ReviewEventsUseCase` с approve/reject/edit/auto-publish + audit trail
- [x] D1 FastAPI API — `src/api/` (app, routes_events, schemas, dependencies) — 12 routes
- [x] D2 Dash app — `src/presentation/dash_app/` (app, callbacks, layout_review, layout_timeline)
- [x] D3 Docker — api-server + dash-ui services в docker-compose.yml
- [x] E1 Playwright — tests/e2e с smoke tests (4 сценария)
- [x] E2 API tests — tests/api с 10 integration tests
- [x] F1 Review use case tests — 7 unit tests
- [x] Streamlit removed — app.py → legacy, dep удалена из pyproject.toml
- [x] OTel — FastAPI instrumented
- [x] AGENTS.md — полностью обновлён
- [x] Ruff расширен (B, SIM, RUF, PT, C4, PIE правила)
- [x] Полный тестовый прогон: **300 passed, 0 failed**

---

## Риски и контроль

- Риск регрессии pipeline -> mitigation: feature flags + integration tests.
- Риск затяжной миграции UI -> mitigation: API-first и side-by-side режим.
- Риск роста сложности -> mitigation: ADR + dependency rules + маленькие инкременты.

---

## Журнал изменений плана

- 2026-03-27: Создана версия v1.
- 2026-03-27: Sprint 1 завершён. Все 19 acceptance criteria выполнены.
  - Добавлено: .editorconfig, justfile, Python 3.12, расширенный ruff
  - Добавлено: ReviewLifecycleStatus, EventAuditEntry, EventVersion в domain
  - Добавлено: Alembic migration + SQLite schema для review lifecycle
  - Добавлено: 10 review методов в SQLiteRepository
  - Добавлено: ReviewEventsUseCase (approve/reject/edit/auto-publish + audit)
  - Добавлено: FastAPI API layer (12 routes, OpenAPI, health, events CRUD, review, timeline, audit)
  - Добавлено: Dash app (review queue + timeline + callbacks)
  - Добавлено: docker-compose api-server + dash-ui сервисы
  - Добавлено: Playwright e2e tests + API integration tests
  - Добавлено: 7 review use case unit tests
  - Удалено: Streamlit из deps, app.py → legacy
  - Тесты: 300 passed, 0 failed
