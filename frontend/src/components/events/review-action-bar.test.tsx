import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ReviewActionBar } from './review-action-bar'

const sampleEvent = {
  event_id: '1',
  title: 'Payments v2 launch',
} as const

describe('ReviewActionBar', () => {
  it('keeps action buttons disabled until actor is set', () => {
    render(
      <ReviewActionBar
        event={sampleEvent as never}
        actor=""
        onActorChange={vi.fn()}
        onAction={vi.fn()}
        isPending={false}
      />,
    )

    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
  })

  it('fires approve callback when actor exists', () => {
    const onAction = vi.fn().mockResolvedValue(undefined)

    render(
      <ReviewActionBar
        event={sampleEvent as never}
        actor="ops-user"
        onActorChange={vi.fn()}
        onAction={onAction}
        isPending={false}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(onAction).toHaveBeenCalledWith('approve', undefined)
  })

  it('resets the note field when a different event is selected', () => {
    const { rerender } = render(
      <ReviewActionBar
        key="event-1"
        event={{ ...sampleEvent, event_id: 'event-1' } as never}
        actor="ops-user"
        onActorChange={vi.fn()}
        onAction={vi.fn()}
        isPending={false}
      />,
    )

    fireEvent.change(screen.getByLabelText('Review note'), {
      target: { value: 'This note should not leak.' },
    })

    rerender(
      <ReviewActionBar
        key="event-2"
        event={{ ...sampleEvent, event_id: 'event-2', title: 'Another event' } as never}
        actor="ops-user"
        onActorChange={vi.fn()}
        onAction={vi.fn()}
        isPending={false}
      />,
    )

    expect(screen.getByLabelText('Review note')).toHaveValue('')
  })
})
