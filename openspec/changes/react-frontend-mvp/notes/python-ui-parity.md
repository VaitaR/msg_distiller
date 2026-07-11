# Python UI Parity

## Current Active Python UI

- Active UI stack: Dash + Plotly
- Entry point: `scripts/run_dash.py`
- App factory: `src/presentation/dash_app/app.py`

## Current Pages

### Review Queue

Current elements:

- Review-status buttons: needs review, approved, published, rejected, all
- Stats badges from `/api/v1/events/stats`
- Table from `/api/v1/events`
- Detail panel from `/api/v1/events/{event_id}`
- Approve, reject, publish actions via `/api/v1/events/{event_id}/review`

### Timeline

Current elements:

- Days filter
- Review-status filter
- Plotly timeline from `/api/v1/events/timeline`

## Business Rules Not To Lose

- Review flows are backend-driven and must stay aligned with current API contracts.
- Selected event detail must use the event detail endpoint rather than stale row data alone.
- Review actions must refresh list or stats views after mutation.
- Timeline must handle empty data without rendering failure.

## MVP Must Have

- Review queue page
- Stats summary
- Review status filtering
- Sortable table
- Event detail panel or drawer
- Approve, reject, publish actions
- Timeline page with range and review-status filters
- Loading, empty, and error states

## Deferred Beyond MVP

- Archive action
- Audit history UI
- Unmerge flow UI
- Advanced inline editing beyond a bounded edit surface
- Real-time updates beyond polling or refetch on focus