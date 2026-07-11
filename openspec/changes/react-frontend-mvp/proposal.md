# React Frontend MVP

## Why

The repository already exposes a usable FastAPI backend and a limited Dash UI for review and timeline workflows. The next step is a modern interactive frontend that improves filtering, navigation, table ergonomics, and data visualization without changing backend contracts or introducing auth complexity.

## Goals

- Replace the current Dash user interaction layer for MVP workflows with a React and TypeScript SPA.
- Preserve backend-driven review queue and timeline flows.
- Centralize API access in a typed client layer.
- Add focused frontend quality gates: typecheck, lint, build, stories, and browser smoke tests.
- Keep scope bounded to review queue and timeline workflows.

## Non-Goals

- Corporate auth or SSO.
- SSR, BFF, or Next.js server features.
- Broad backend refactors or API contract redesign.
- Full audit-history UI beyond what is needed for MVP confidence.
- Large design-system investment beyond reusable primitives needed by this MVP.

## Scope

The MVP includes:

- Review Queue page with status filters, stats summary, sortable table, selection, detail panel, and review actions.
- Timeline page with range filter, review-status filter, chart visualization, and event detail view.
- Backend-backed loading, error, and empty states.
- Storybook coverage for important reusable UI states.
- Playwright smoke flows for the main browser scenarios.

## Allowed Paths

- frontend/**
- openspec/changes/react-frontend-mvp/**
- README.md
- AGENTS.md
- .gitignore

## Success Criteria

- Local frontend dev server starts successfully.
- Backend-backed review and timeline flows work against the existing API.
- Build, lint, and typecheck pass for the frontend.
- Playwright smoke tests pass for main flows.
- Independent reviewer returns PASS or PASS WITH MINOR ISSUES.