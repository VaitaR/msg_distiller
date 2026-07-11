import { useEffect, useState } from 'react'

import type { EventRecord, ReviewAction } from '../../features/events/types'
import { Button } from '../ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Input } from '../ui/input'
import { Textarea } from '../ui/textarea'

export function ReviewActionBar({
  event,
  actor,
  onActorChange,
  onAction,
  isPending,
}: {
  event: EventRecord | null
  actor: string
  onActorChange: (value: string) => void
  onAction: (action: ReviewAction, note?: string) => Promise<void>
  isPending: boolean
}) {
  const [message, setMessage] = useState<string | null>(null)
  const [note, setNote] = useState('')

  useEffect(() => {
    if (!message) {
      return
    }

    const timer = window.setTimeout(() => setMessage(null), 3500)
    return () => window.clearTimeout(timer)
  }, [message])

  const canAct = Boolean(event) && actor.trim().length > 0 && !isPending

  async function runAction(action: ReviewAction) {
    if (!event) {
      return
    }

    try {
      await onAction(action, note.trim() || undefined)
      setMessage(`${action} completed for ${event.title}`)
      setNote('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Action failed')
    }
  }

  return (
    <Card data-testid="review-action-bar">
      <CardHeader>
        <CardTitle>Review actions</CardTitle>
        <CardDescription>Set a local actor name for backend review mutations.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="actor-name">
            Reviewer name
          </label>
          <Input
            id="actor-name"
            placeholder="ops-analyst"
            value={actor}
            onChange={(event) => onActorChange(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="review-note">
            Review note
          </label>
          <Textarea
            id="review-note"
            placeholder="Optional context for rejection or publication decisions"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            className="min-h-20"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!canAct} onClick={() => runAction('approve')}>
            Approve
          </Button>
          <Button variant="destructive" disabled={!canAct} onClick={() => runAction('reject')}>
            Reject
          </Button>
          <Button variant="secondary" disabled={!canAct} onClick={() => runAction('publish')}>
            Publish
          </Button>
        </div>
        {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
      </CardContent>
    </Card>
  )
}