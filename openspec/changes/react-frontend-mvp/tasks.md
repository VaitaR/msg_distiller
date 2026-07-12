# Tasks

## 1. Discovery and Scope

- [x] Confirm backend entrypoints and API surface.
- [x] Confirm current Dash UI pages and core flows.
- [x] Decide frontend architecture for MVP.
- [x] Record backend inventory and MVP parity notes.

## 2. Frontend Foundation

- [x] Scaffold isolated Vite + React + TypeScript frontend in `frontend/`.
- [x] Configure Tailwind CSS and shadcn-style UI primitives.
- [x] Configure React Router, TanStack Query, and shared API client.
- [x] Add Storybook and Playwright setup.

## 3. Review Queue MVP

- [x] Implement review page layout and navigation shell.
- [x] Implement stats summary and status filters.
- [x] Implement event table with sorting and pagination-ready structure.
- [x] Implement event detail panel.
- [x] Implement approve, reject, and publish actions.

## 4. Timeline MVP

- [x] Implement timeline page filters.
- [x] Implement ECharts timeline visualization.
- [x] Reuse event detail view from selected chart item.

## 5. Quality and Validation

- [x] Add focused unit or component tests where they add confidence.
- [x] Add Storybook stories for critical states.
- [x] Add Playwright smoke coverage for review and timeline flows.
- [x] Run build, lint, typecheck, tests, and browser validation.

## 6. Review Loop

- [x] Run strict independent review.
- [x] Fix blocking findings.
- [x] Re-run validation and review until no blocking issues remain.
