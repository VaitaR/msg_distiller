# Audit Summary

## Scope

- Backend API and review workflow surfaces
- Repository persistence behavior relevant to public mutation paths
- CI and validation coverage for backend and frontend

## Accepted Findings

1. `AUD-001` — unauthenticated mutation routes are exposed over a broad network/CORS surface.
2. `AUD-002` — the PATCH path allows arbitrary field mutation and unsafe dynamic SQL field handling.
3. `AUD-003` — the list endpoint reports page size as `total`, so pagination metadata is wrong.
4. `AUD-004` — CI does not run any frontend quality gates.
5. `AUD-005` — CI tries to upload `coverage.xml` without generating it.

## Local Validation Performed

- Reproduced workflow bypass: patched `review_status` from `needs_review` to `published` through `PATCH /api/v1/events/{id}` using a bare TestClient request with no auth headers.
- Reproduced dynamic-field failure: patched an unknown key and observed `500 Internal Server Error` from the same endpoint.
- Reproduced pagination metadata bug: requested `limit=1` on a seeded 15-event DB and received `total=1`.
- Verified CI coverage mismatch: ran the workflow-equivalent pytest coverage command and confirmed `coverage.xml` was not produced.

## Suggested Remediation Order

1. Lock down the API write surface: auth, authorization, restricted bind host, explicit CORS allowlist.
2. Replace free-form patching with a typed editable-field contract and hard-coded repository column mapping.
3. Fix list-count semantics before expanding frontend pagination.
4. Add frontend validation jobs to CI.
5. Repair the coverage upload path so CI observability matches reality.
