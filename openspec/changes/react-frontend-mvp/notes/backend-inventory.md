# Backend Inventory

## Runtime

- Framework: FastAPI
- API app: `src/api/app.py`
- Server entrypoint: `scripts/run_api_server.py`
- Default local API URL: `http://localhost:8000`
- OpenAPI: `/api/openapi.json`
- Docs: `/api/docs`

## MVP-Relevant Endpoints

- `GET /api/v1/health`
- `GET /api/v1/events`
- `GET /api/v1/events/stats`
- `GET /api/v1/events/timeline`
- `GET /api/v1/events/{event_id}`
- `POST /api/v1/events/{event_id}/review`
- `PATCH /api/v1/events/{event_id}`
- `GET /api/v1/events/{event_id}/audit`

## Current Query Surface

### `GET /api/v1/events`

Params:

- `review_status`: optional
- `limit`: default 50, max 500
- `offset`: default 0

Response:

- `items`: `EventResponse[]`
- `total`
- `limit`
- `offset`

Note: current `total` is the returned page length, not a separate total-count query.

### `GET /api/v1/events/stats`

Response keys:

- `needs_review`
- `approved`
- `published`
- `rejected`
- `archived`

### `GET /api/v1/events/timeline`

Params:

- `days`: default 30
- `review_status`: optional

Response:

- `entries`: `TimelineEntry[]`
- `total`

### `POST /api/v1/events/{event_id}/review`

Body:

- `action`: `approve | reject | publish | archive`
- `actor`: string
- `note`: optional

Important: the route currently handles `approve`, `reject`, and `publish`. `archive` is present in schema text but not wired in the route handler, so the frontend MVP must not expose archive until backend support exists.

## Seed Data

- Deterministic test dataset defined in `tests/factories.py`
- 15 seeded events across review statuses and Slack or Telegram sources
- API tests: `tests/api/test_events_api.py`
- Existing browser tests: `tests/e2e/test_dash_smoke.py`