# Frontend Architecture

## Decision

Use Vite with React and TypeScript for the frontend MVP.

## Why Vite

- Existing backend already owns API and runtime concerns.
- No SSR or SSO requirement.
- Lower operational cost than introducing Next.js.
- Faster bootstrap and iteration for a Python-first repository.

## Proposed Frontend Stack

- React
- TypeScript strict mode
- React Router
- Tailwind CSS
- shadcn-style UI primitives
- TanStack Query
- TanStack Table
- ECharts
- Storybook
- Playwright

## Proposed Structure

```text
frontend/
  src/
    app/
    components/
      ui/
      layout/
      events/
    features/
      events/
      review/
      timeline/
    lib/
    pages/
    stories/
  e2e/
```

## MVP Pages

- `/review`
- `/timeline`

## Shared Data Strategy

- One centralized fetch client
- TanStack Query for server state
- Query invalidation after review mutations
- URL search params for page filters where it does not overcomplicate MVP

## Known Risks

- Backend list endpoint does not yet provide a true total count.
- Archive action is not implemented in the route handler.
- Current API accepts free-form patch payloads, so frontend editing must stay intentionally narrow.
