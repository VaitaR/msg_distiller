# Frontend MVP

React and TypeScript frontend MVP for review queue and timeline workflows on top of the existing FastAPI backend.

## Stack

- Vite
- React
- TypeScript
- Tailwind CSS
- TanStack Query
- TanStack Table
- ECharts
- Storybook
- Playwright
- Vitest

## Commands

- `npm install`
- `npm run dev`
- `npm run build`
- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run test:e2e`
- `npm run test:e2e:real`
- `npm run storybook`
- `npm run build-storybook`

## Environment

- `VITE_API_BASE_URL`
  - optional
  - defaults to `http://localhost:8000`

## Local Development

1. Start the backend API from the repository root:
   - `just api`
   - or `uv run python scripts/run_api_server.py`
2. In `frontend/`, run `npm run dev`
3. Open `http://localhost:5173/review`

## Browser Smoke Tests

`npm run test:e2e` starts a fresh isolated pair of local servers on every run:

- a seeded FastAPI backend on `http://127.0.0.1:18000`
- the Vite dev server on `http://127.0.0.1:4173`

The command does not reuse already-running listeners on those ports.

Artifacts are written to:

- `frontend/playwright-report/`
- `frontend/playwright-report-real/`
- `frontend/test-results/` when failures occur

`npm run test:e2e:real` starts the FastAPI API against `data/slack_events.db` and runs the browser suite against that local snapshot instead of the seeded fixture backend.

## MVP Scope

- Review queue with status filters, stats, detail panel, bounded edit form, and review actions
- Timeline page with days filter, review-status filter, and event drill-down
- Loading, error, and empty states

## Known Limitations

- Timeline chunk remains heavy because ECharts is isolated into the timeline route but still substantial.
- Archive is not exposed yet. Unmerge is available from the event investigation panel when absorbed relations exist.
- Edit surface is intentionally narrow: title, summary, and why-it-matters only.
- Backend list pagination uses the current API total field, which is not yet a true separate count.
