import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { EmptyState } from '../../components/events/empty-state'
import { ErrorState } from '../../components/events/error-state'
import { EventDetailPanel } from '../../components/events/event-detail-panel'
import { EventsTable } from '../../components/events/events-table'
import { LoadingState } from '../../components/events/loading-state'
import { ReviewActionBar } from '../../components/events/review-action-bar'
import { ReviewStatsBar } from '../../components/events/review-stats-bar'
import { ReviewStatusTabs } from '../../components/events/review-status-tabs'
import { Input } from '../../components/ui/input'
import { usePatchEventMutation, useReviewActionMutation } from '../../features/events/mutations'
import { useEventDetail, useEvents, useReviewStats } from '../../features/events/queries'
import type { EventRecord, ReviewStatus } from '../../features/events/types'

function readStatus(searchParams: URLSearchParams): ReviewStatus | 'all' {
  const value = searchParams.get('status')
  if (
    value === 'needs_review' ||
    value === 'approved' ||
    value === 'published' ||
    value === 'rejected' ||
    value === 'archived'
  ) {
    return value
  }

  if (value === 'all') {
    return 'all'
  }

  return 'needs_review'
}

export function ReviewQueuePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [actor, setActor] = useState(() => window.localStorage.getItem('review-actor') ?? '')
  const [searchValue, setSearchValue] = useState('')
  const currentStatus = readStatus(searchParams)
  const selectedEventId = searchParams.get('event')

  const eventsQuery = useEvents({
    reviewStatus: currentStatus === 'all' ? undefined : currentStatus,
    limit: 200,
  })
  const statsQuery = useReviewStats()
  const detailQuery = useEventDetail(selectedEventId)
  const reviewMutation = useReviewActionMutation()
  const patchMutation = usePatchEventMutation()

  const items = useMemo(() => eventsQuery.data?.items ?? [], [eventsQuery.data?.items])
  const filteredItems = useMemo(() => {
    const query = searchValue.trim().toLowerCase()
    if (!query) {
      return items
    }

    return items.filter((item) => {
      const haystack = [
        item.title,
        item.object_name_raw,
        item.summary,
        item.source_id,
        item.category,
        item.message_id,
        ...item.source_channels,
      ]
        .join(' ')
        .toLowerCase()

      return haystack.includes(query)
    })
  }, [items, searchValue])

  const selectedEvent: EventRecord | null = (() => {
    if (!selectedEventId) {
      return null
    }

    return detailQuery.data ?? items.find((item) => item.event_id === selectedEventId) ?? null
  })()

  function updateSearch(next: { status?: ReviewStatus | 'all'; event?: string | null }) {
    const nextParams = new URLSearchParams(searchParams)

    if (next.status) {
      nextParams.set('status', next.status)
    }

    if (next.event) {
      nextParams.set('event', next.event)
    } else if (next.event === null) {
      nextParams.delete('event')
    }

    setSearchParams(nextParams)
  }

  function handleActorChange(value: string) {
    setActor(value)
    window.localStorage.setItem('review-actor', value)
  }

  if (eventsQuery.isLoading || statsQuery.isLoading) {
    return <LoadingState lines={6} />
  }

  if (eventsQuery.isError || statsQuery.isError) {
    return (
      <ErrorState
        title="Could not load review data"
        description="Check the API server and the VITE_API_BASE_URL setting, then retry."
        onRetry={() => {
          void eventsQuery.refetch()
          void statsQuery.refetch()
        }}
      />
    )
  }

  return (
    <div className="space-y-6">
      <section className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-primary/80">MVP flow</p>
            <h2 className="text-3xl">Review extracted events</h2>
            <p className="max-w-2xl text-sm text-muted-foreground">
              Validate the queue, inspect details, make bounded edits, and promote only the events worth publishing.
            </p>
          </div>
          <ReviewStatusTabs
            value={currentStatus}
            onChange={(value) => updateSearch({ status: value, event: null })}
          />
        </div>
        {statsQuery.data ? <ReviewStatsBar stats={statsQuery.data} /> : null}
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_240px]">
          <Input
            placeholder="Search title, object, summary, source, or message ID"
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)}
          />
          <div className="rounded-full border border-input bg-white/75 px-4 py-2 text-sm text-muted-foreground">
            Showing {filteredItems.length} of {items.length} events
          </div>
        </div>
      </section>

      {filteredItems.length === 0 ? (
        <EmptyState
          title={items.length === 0 ? 'No events in this queue' : 'No events match this search'}
          description={
            items.length === 0
              ? 'Try another review status or wait for the next extraction cycle.'
              : 'Clear or broaden the local search to inspect more events in the current queue.'
          }
        />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(340px,0.9fr)]">
          <div className="space-y-6">
            <EventsTable items={filteredItems} selectedEventId={selectedEventId} onSelect={(eventId) => updateSearch({ event: eventId })} />
            <ReviewActionBar
              key={selectedEvent?.event_id ?? 'empty'}
              event={selectedEvent}
              actor={actor}
              onActorChange={handleActorChange}
              isPending={reviewMutation.isPending}
              onAction={async (action, note) => {
                await reviewMutation.mutateAsync({
                  action,
                  actor,
                  eventId: selectedEvent?.event_id ?? '',
                  note,
                })
              }}
            />
          </div>
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