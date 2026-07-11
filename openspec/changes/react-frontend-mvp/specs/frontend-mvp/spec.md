# Frontend MVP Spec

## Summary

Build a React and TypeScript single-page application for event review and timeline analysis on top of the existing FastAPI backend.

## Requirements

### Requirement: Review Queue

The system shall provide a review queue page backed by the existing events API.

#### Scenario: Load default review queue

- **WHEN** the user opens the review page
- **THEN** the application shall request event stats and review-queue items from the backend
- **AND** display loading state until data resolves
- **AND** show an empty state when no matching events exist
- **AND** show an error state when the API request fails

#### Scenario: Filter by review status

- **WHEN** the user changes the review status filter
- **THEN** the application shall request the corresponding filtered event list
- **AND** reflect the filter in URL search params when practical for MVP

#### Scenario: Review an event

- **WHEN** the user selects an event and triggers approve, reject, or publish
- **THEN** the application shall call the review action endpoint
- **AND** refresh the relevant list, stats, and detail data on success
- **AND** display a visible success or failure message

### Requirement: Event Detail

The system shall expose a detailed view for a selected event.

#### Scenario: Inspect selected event

- **WHEN** the user selects an event from the review table or timeline
- **THEN** the application shall show key fields including title, summary, category, confidence, importance, source, and review status

### Requirement: Timeline Analysis

The system shall provide a timeline analysis page backed by the existing timeline endpoint.

#### Scenario: View timeline entries

- **WHEN** the user opens the timeline page
- **THEN** the application shall request timeline entries from the backend
- **AND** render them in a chart with visible labels and empty state handling

#### Scenario: Adjust timeline filters

- **WHEN** the user changes days or review-status filters
- **THEN** the application shall refresh the timeline query and update the visualization

### Requirement: Frontend Quality Gates

The system shall include focused frontend quality validation appropriate for MVP.

#### Scenario: Validate frontend changes

- **WHEN** frontend implementation changes are made
- **THEN** the repository shall provide commands for install, dev, build, lint, typecheck, storybook, and smoke tests
- **AND** Playwright shall cover the main review and timeline flows
- **AND** key reusable components shall have stories for loading, empty, error, or success states where applicable