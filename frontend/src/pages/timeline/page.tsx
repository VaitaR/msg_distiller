import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import { EmptyState } from '../../components/events/empty-state'
import { ErrorState } from '../../components/events/error-state'
import { AnalysisDashboard } from '../../components/events/analysis-dashboard'
import { EventDetailPanel } from '../../components/events/event-detail-panel'
import { LoadingState } from '../../components/events/loading-state'
import { TimelineFilters } from '../../components/events/timeline-filters'
import { usePatchEventMutation } from '../../features/events/mutations'
import { useEventDetail, useTimeline } from '../../features/events/queries'
import type { ReviewStatus } from '../../features/events/types'

function readTimelineStatus(searchParams: URLSearchParams): ReviewStatus | 'all' {
  const value = searchParams.get('reviewStatus')
  if (
    value === 'needs_review' ||
    value === 'approved' ||
    value === 'published' ||
    value === 'rejected' ||
    value === 'archived'
  ) {
    return value
  }

  return 'all'
}

export function TimelinePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedEventId = searchParams.get('event')
  const reviewStatus = readTimelineStatus(searchParams)
  const days = Number(searchParams.get('days') ?? '30')
  const actor = window.localStorage.getItem('review-actor') ?? ''

  const timelineQuery = useTimeline({
    days,
    reviewStatus: reviewStatus === 'all' ? undefined : reviewStatus,
  })
  const detailQuery = useEventDetail(selectedEventId)
  const patchMutation = usePatchEventMutation()

  const selectedEvent = useMemo(() => detailQuery.data ?? null, [detailQuery.data])

  function updateSearch(values: { days?: number; reviewStatus?: ReviewStatus | 'all'; event?: string | null }) {
    const nextParams = new URLSearchParams(searchParams)

    if (values.days) {
      nextParams.set('days', String(values.days))
    }

    if (values.reviewStatus) {
      nextParams.set('reviewStatus', values.reviewStatus)
    }

    if (values.event) {
      nextParams.set('event', values.event)
    } else if (values.event === null) {
      nextParams.delete('event')
    }

    setSearchParams(nextParams)
  }

  if (timelineQuery.isLoading) {
    return <LoadingState lines={5} />
  }

  if (timelineQuery.isError) {
    return (
      <ErrorState
        title="Could not load timeline"
        description="The timeline endpoint did not respond. Verify the backend and retry."
        onRetry={() => void timelineQuery.refetch()}
      />
    )
  }

  const entries = timelineQuery.data?.entries ?? []

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-[0.22em] text-primary/80">Analysis view</p>
        <h2 className="text-3xl">Event analysis workspace</h2>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Move from raw chronology to actual operational analysis: volume, category mix, backlog by source, priority outliers, and then drill into the same investigation panel used by review.
        </p>
      </section>

      <TimelineFilters
        days={days}
        reviewStatus={reviewStatus}
        onDaysChange={(value) => updateSearch({ days: value, event: null })}
        onReviewStatusChange={(value) => updateSearch({ reviewStatus: value, event: null })}
      />

      {entries.length === 0 ? (
        <EmptyState
          title="No events in this time window"
          description="Widen the date range or switch the review-state filter to inspect more entries."
        />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(360px,0.85fr)]">
          <AnalysisDashboard entries={entries} onSelect={(eventId) => updateSearch({ event: eventId })} />
          <EventDetailPanel
            key={selectedEvent?.event_id ?? 'empty'}
            event={selectedEvent}
            actor={actor}
            isSaving={patchMutation.isPending}
            onSave={async (updates) => {
              await patchMutation.mutateAsync({
                actor,
                eventId: selectedEvent?.event_id ?? '',
                updates,
              })
            }}
          />
        </div>
      )}
    </div>
  )
}