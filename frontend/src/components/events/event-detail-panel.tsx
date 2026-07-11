import { useEffect, useState } from 'react'

import { useUnmergeMutation } from '../../features/events/mutations'
import {
  useEventAudit,
  useEventMessageMetadata,
  useEventRelations,
  useEventVersions,
} from '../../features/events/queries'
import type { EventRecord } from '../../features/events/types'
import { cn, formatDate, formatPercent } from '../../lib/utils'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Input } from '../ui/input'
import { Textarea } from '../ui/textarea'

type EditableFields = Pick<EventRecord, 'title' | 'summary' | 'why_it_matters'>
type DetailTab = 'overview' | 'source' | 'history' | 'relations'

function humanizeToken(value: string | null | undefined) {
  if (!value) {
    return 'N/A'
  }

  return value.replace(/_/g, ' ')
}

function renderPrimitive(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return 'N/A'
  }

  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }

  return JSON.stringify(value)
}

function statusVariant(status: string) {
  if (status === 'published' || status === 'approved') {
    return 'success'
  }
  if (status === 'rejected') {
    return 'danger'
  }
  if (status === 'needs_review') {
    return 'warning'
  }
  return 'default'
}

export function EventDetailPanel({
  event,
  actor,
  onSave,
  isSaving,
}: {
  event: EventRecord | null
  actor: string
  onSave: (updates: EditableFields) => Promise<void>
  isSaving: boolean
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [activeTab, setActiveTab] = useState<DetailTab>('overview')
  const [message, setMessage] = useState<string | null>(null)

  const auditQuery = useEventAudit(event?.event_id ?? null)
  const relationsQuery = useEventRelations(event?.event_id ?? null)
  const versionsQuery = useEventVersions(event?.event_id ?? null)
  const messageMetadataQuery = useEventMessageMetadata(event?.event_id ?? null)
  const unmergeMutation = useUnmergeMutation()

  useEffect(() => {
    if (!message) {
      return
    }

    const timer = window.setTimeout(() => setMessage(null), 4000)
    return () => window.clearTimeout(timer)
  }, [message])

  if (!event) {
    return (
      <Card className="h-full" data-testid="event-detail-panel">
        <CardHeader>
          <CardTitle>Event investigation</CardTitle>
          <CardDescription>Select an event from the queue or analysis view to inspect provenance, history, and source context.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  const auditEntries = auditQuery.data ?? []
  const relations = relationsQuery.data ?? []
  const versions = versionsQuery.data ?? []
  const metadata = messageMetadataQuery.data
  const hasAbsorbedRelations = relations.some((relation) => relation.relation_type === 'absorbed_from')

  async function handleUnmerge() {
    if (!event || actor.trim().length === 0) {
      return
    }

    const currentEvent = event

    try {
      const result = await unmergeMutation.mutateAsync({
        eventId: currentEvent.event_id,
        actor,
      })
      const restoredCount = result.restored_event_ids.length
      setMessage(restoredCount > 0 ? `Unmerge restored ${restoredCount} absorbed events.` : 'No absorbed events were available to restore.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unmerge failed')
    }
  }

  function tabButton(tab: DetailTab, label: string) {
    return (
      <button
        type="button"
        onClick={() => setActiveTab(tab)}
        className={cn(
          'rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] transition',
          activeTab === tab ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground hover:bg-secondary/70',
        )}
      >
        {label}
      </button>
    )
  }

  return (
    <Card className="h-full" data-testid="event-detail-panel">
      <CardHeader>
        <div className="flex flex-col gap-4">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <Badge variant={statusVariant(event.review_status)}>{humanizeToken(event.review_status)}</Badge>
                <Badge variant="info">{humanizeToken(event.source_id)}</Badge>
                <Badge>{humanizeToken(event.category)}</Badge>
                <Badge>{humanizeToken(event.action)}</Badge>
              </div>
              <div>
                <CardTitle>{event.title}</CardTitle>
                <CardDescription>
                  {humanizeToken(event.change_type)} · {humanizeToken(event.environment)} · version {event.version}
                </CardDescription>
              </div>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              {hasAbsorbedRelations ? (
                <Button variant="secondary" size="sm" disabled={unmergeMutation.isPending || actor.trim().length === 0} onClick={() => void handleUnmerge()}>
                  {unmergeMutation.isPending ? 'Unmerging…' : 'Unmerge absorbed'}
                </Button>
              ) : null}
              <Button variant="outline" size="sm" onClick={() => setIsEditing((open) => !open)}>
                {isEditing ? 'Cancel edit' : 'Edit fields'}
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {tabButton('overview', 'Overview')}
            {tabButton('source', 'Source')}
            {tabButton('history', 'History')}
            {tabButton('relations', 'Relations')}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}

        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Confidence</dt>
            <dd className="font-medium">{formatPercent(event.confidence)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Importance</dt>
            <dd className="font-medium">{event.importance}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Extracted</dt>
            <dd className="font-medium">{formatDate(event.extracted_at)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Reviewed</dt>
            <dd className="font-medium">{event.reviewed_at ? formatDate(event.reviewed_at) : 'Not yet'}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Event date</dt>
            <dd className="font-medium">{formatDate(event.event_date)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Message published</dt>
            <dd className="font-medium">{formatDate(event.message_published_at)}</dd>
          </div>
        </dl>

        {isEditing ? (
          <form
            className="space-y-4"
            onSubmit={async (formEvent) => {
              formEvent.preventDefault()
              const formData = new FormData(formEvent.currentTarget)
              await onSave({
                title: String(formData.get('title') ?? ''),
                summary: String(formData.get('summary') ?? ''),
                why_it_matters: String(formData.get('why_it_matters') ?? ''),
              })
              setIsEditing(false)
            }}
          >
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="event-title">
                Title
              </label>
              <Input id="event-title" name="title" defaultValue={event.title} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="event-summary">
                Summary
              </label>
              <Textarea id="event-summary" name="summary" defaultValue={event.summary} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="event-impact">
                Why it matters
              </label>
              <Textarea id="event-impact" name="why_it_matters" defaultValue={event.why_it_matters ?? ''} />
            </div>
            <p className="text-xs text-muted-foreground">
              Changes are sent with actor <span className="font-medium text-foreground">{actor || 'unset'}</span>.
            </p>
            <Button type="submit" disabled={isSaving || actor.trim().length === 0}>
              {isSaving ? 'Saving…' : 'Save changes'}
            </Button>
          </form>
        ) : activeTab === 'overview' ? (
          <div className="space-y-4 text-sm">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Summary</p>
              <p>{event.summary}</p>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Why it matters</p>
              <p>{event.why_it_matters ?? 'Not provided yet.'}</p>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Impact areas</p>
              <p>{event.impact_area.length > 0 ? event.impact_area.join(', ') : 'Not specified.'}</p>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Impact types</p>
              <p>{event.impact_type.length > 0 ? event.impact_type.map((value) => humanizeToken(value)).join(', ') : 'Not specified.'}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Object</p>
                <p>{event.object_name_raw}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Object ID</p>
                <p>{event.object_id ?? 'Not linked.'}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Anchor</p>
                <p>{event.anchor ?? 'Not provided.'}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Stroke</p>
                <p>{event.stroke ?? 'Not provided.'}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Time source</p>
                <p>
                  {humanizeToken(event.time_source)} · {formatPercent(event.time_confidence)}
                </p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Severity</p>
                <p>{event.severity ? humanizeToken(event.severity) : 'N/A'}</p>
              </div>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Qualifiers and anchors</p>
              <div className="flex flex-wrap gap-2">
                {event.qualifiers.map((qualifier) => (
                  <Badge key={qualifier}>{qualifier}</Badge>
                ))}
                {event.anchors.map((anchorValue) => (
                  <Badge key={anchorValue} variant="info">
                    {anchorValue}
                  </Badge>
                ))}
                {event.qualifiers.length === 0 && event.anchors.length === 0 ? <span className="text-muted-foreground">No qualifiers or anchors.</span> : null}
              </div>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Keys</p>
              <div className="space-y-1 font-mono text-xs text-muted-foreground">
                <p>cluster_key: {event.cluster_key}</p>
                <p>dedup_key: {event.dedup_key}</p>
              </div>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Links</p>
              {event.links.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {event.links.map((link) => (
                    <a key={link} href={link} target="_blank" rel="noreferrer" className="truncate text-primary underline-offset-4 hover:underline">
                      {link}
                    </a>
                  ))}
                </div>
              ) : (
                <p>No links attached.</p>
              )}
            </div>
          </div>
        ) : activeTab === 'source' ? (
          <div className="space-y-4 text-sm" data-testid="event-source-context">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Message ID</p>
                <p className="font-mono text-xs">{event.message_id}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Source channels</p>
                <p>{event.source_channels.length > 0 ? event.source_channels.join(', ') : 'Unknown'}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Replies</p>
                <p>{messageMetadataQuery.isLoading ? 'Loading…' : metadata?.reply_count ?? 0}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Reactions</p>
                <p>{messageMetadataQuery.isLoading ? 'Loading…' : metadata?.reactions_count ?? 0}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">File attached</p>
                <p>{messageMetadataQuery.isLoading ? 'Loading…' : metadata?.has_file ? 'Yes' : 'No'}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Forwarded from</p>
                <p>{messageMetadataQuery.isLoading ? 'Loading…' : metadata?.forwarded_from ?? 'N/A'}</p>
              </div>
            </div>
            {messageMetadataQuery.isError ? <p className="text-muted-foreground">Could not load message metadata.</p> : null}
            <div className="flex flex-col gap-2">
              {metadata?.permalink ? (
                <a href={metadata.permalink} target="_blank" rel="noreferrer" className="text-primary underline-offset-4 hover:underline">
                  Open Slack permalink
                </a>
              ) : null}
              {metadata?.post_url ? (
                <a href={metadata.post_url} target="_blank" rel="noreferrer" className="text-primary underline-offset-4 hover:underline">
                  Open Telegram post
                </a>
              ) : null}
              {metadata?.file_mime ? <p className="text-muted-foreground">File mime: {metadata.file_mime}</p> : null}
            </div>
          </div>
        ) : activeTab === 'history' ? (
          <div className="space-y-5 text-sm">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Audit trail</p>
              {auditQuery.isLoading ? (
                <p>Loading audit entries…</p>
              ) : auditEntries.length > 0 ? (
                <div className="space-y-3" data-testid="event-audit-list">
                  {auditEntries.map((entry) => (
                    <div key={entry.audit_id} className="rounded-3xl border border-border bg-white/60 p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={statusVariant(entry.action)}>{humanizeToken(entry.action)}</Badge>
                        <Badge>{humanizeToken(entry.origin)}</Badge>
                        <span className="text-xs text-muted-foreground">v{entry.version}</span>
                      </div>
                      <p className="mt-2 text-sm font-medium">{entry.actor} · {formatDate(entry.timestamp)}</p>
                      <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                        {Object.entries(entry.changes).map(([field, value]) => (
                          <p key={field}>
                            {field}: {renderPrimitive(value)}
                          </p>
                        ))}
                      </div>
                      {entry.note ? <p className="mt-2 text-sm">{entry.note}</p> : null}
                    </div>
                  ))}
                </div>
              ) : (
                <p>No audit entries yet.</p>
              )}
            </div>
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Version snapshots</p>
              {versionsQuery.isLoading ? (
                <p>Loading versions…</p>
              ) : versions.length > 0 ? (
                <div className="space-y-2">
                  {versions.slice(0, 6).map((version) => (
                    <div key={version.version_id} className="rounded-3xl border border-border bg-white/60 p-4">
                      <p className="font-medium">Version {version.version}</p>
                      <p className="text-xs text-muted-foreground">{humanizeToken(version.origin)} · {formatDate(version.created_at)}</p>
                      <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                        <p>summary: {renderPrimitive(version.snapshot['summary'])}</p>
                        <p>review_status: {renderPrimitive(version.snapshot['review_status'])}</p>
                        <p>importance: {renderPrimitive(version.snapshot['importance'])}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p>No historical versions saved yet.</p>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-4 text-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Relations</p>
            {relationsQuery.isLoading ? (
              <p>Loading relations…</p>
            ) : relations.length > 0 ? (
              <div className="space-y-3" data-testid="event-relations-list">
                {relations.map((relation) => (
                  <div key={`${relation.relation_type}-${relation.target_event_id}`} className="rounded-3xl border border-border bg-white/60 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={relation.relation_type === 'absorbed_from' ? 'warning' : 'default'}>
                        {humanizeToken(relation.relation_type)}
                      </Badge>
                      <span className="font-mono text-xs text-muted-foreground">{relation.target_event_id}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p>No related events are attached to this event.</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}