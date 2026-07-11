import { expect, test } from '@playwright/test'

function buildMockEvent(eventId: string, overrides: Record<string, unknown> = {}) {
  return {
    event_id: eventId,
    message_id: 'msg-seed-099',
    source_channels: ['#timeline'],
    title: 'Approved launch window',
    action: 'launch',
    object_id: 'timeline-launch',
    object_name_raw: 'Timeline launch',
    qualifiers: [],
    stroke: 'General availability',
    anchor: 'timeline',
    category: 'product',
    status: 'completed',
    change_type: 'release',
    environment: 'production',
    severity: 'medium',
    confidence: 0.91,
    importance: 77,
    message_published_at: '2026-03-01T09:30:00Z',
    summary: 'Approved launch window is visible on the timeline.',
    why_it_matters: 'Confirms timeline drill-down after filtering.',
    links: ['https://example.com/timeline-launch'],
    anchors: ['timeline'],
    impact_area: ['timeline'],
    impact_type: ['conversion'],
    time_source: 'message',
    time_confidence: 0.9,
    cluster_key: 'cluster-timeline-launch',
    dedup_key: 'dedup-timeline-launch',
    source_id: 'slack',
    review_status: 'approved',
    reviewed_by: 'frontend-smoke',
    reviewed_at: '2026-03-07T10:00:00Z',
    version: 1,
    origin: 'ai_extraction',
    extracted_at: '2026-03-01T10:00:00Z',
    planned_start: '2026-03-01T10:00:00Z',
    planned_end: '2026-03-07T10:00:00Z',
    actual_start: '2026-03-01T10:00:00Z',
    actual_end: '2026-03-07T10:00:00Z',
    event_date: '2026-03-01T10:00:00Z',
    ...overrides,
  }
}

async function mockInvestigationRoutes(
  page: Parameters<typeof test>[0]['page'],
  eventId: string,
  overrides: Record<string, unknown> = {},
) {
  await page.route(`**/api/v1/events/${eventId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildMockEvent(eventId, overrides)),
    })
  })

  await page.route(`**/api/v1/events/${eventId}/audit`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          audit_id: 'audit-1',
          event_id: eventId,
          version: 1,
          action: 'approve',
          origin: 'human_review',
          changes: { review_status: 'approved', importance: 77 },
          actor: 'frontend-smoke',
          timestamp: '2026-03-07T10:00:00Z',
          note: 'Promoted after manual verification.',
        },
      ]),
    })
  })

  await page.route(`**/api/v1/events/${eventId}/versions`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          version_id: 'version-1',
          event_id: eventId,
          version: 1,
          origin: 'ai_extraction',
          snapshot: {
            summary: 'Approved launch window is visible on the timeline.',
            review_status: 'approved',
            importance: 77,
          },
          created_at: '2026-03-01T10:00:00Z',
        },
      ]),
    })
  })

  await page.route(`**/api/v1/events/${eventId}/relations`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          relation_type: 'absorbed_from',
          target_event_id: '00000000-0000-0000-0000-000000000188',
        },
      ]),
    })
  })

  await page.route(`**/api/v1/events/${eventId}/message-metadata`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        permalink: 'https://slack.test/permalink',
        post_url: null,
        forwarded_from: 'releases-bot',
        reply_count: 3,
        reactions_count: 5,
        has_file: true,
        file_mime: 'application/pdf',
      }),
    })
  })
}

function collectConsoleErrors(page: Parameters<typeof test>[0]['page']) {
  const consoleErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })

  return consoleErrors
}

test('review queue loads seeded events and supports approve flow', async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page)

  await page.goto('/review?status=needs_review')

  await expect(page.getByRole('heading', { name: 'Review extracted events' })).toBeVisible()
  await expect(page.getByText('Needs Review: 5')).toBeVisible()

  const rows = page.getByTestId('events-row')
  await expect(rows).toHaveCount(5)

  await rows.first().click()
  const detailPanel = page.getByTestId('event-detail-panel')
  await expect(detailPanel).toBeVisible()
  await detailPanel.getByRole('button', { name: 'Source' }).click()
  await expect(page.getByTestId('event-source-context')).toBeVisible()

  await page.getByLabel('Reviewer name').fill('frontend-smoke')
  await page.getByTestId('review-action-bar').getByRole('button', { name: 'Approve' }).click()

  await expect(page.getByText(/approve completed/i)).toBeVisible()
  expect(consoleErrors).toEqual([])
})

test('timeline loads backend data and renders the chart shell', async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page)

  await page.goto('/timeline?days=90')

  await expect(page.getByRole('heading', { name: 'Event analysis workspace' })).toBeVisible()
  await expect(page.getByTestId('analysis-dashboard')).toBeVisible()
  await expect(page.getByTestId('analysis-daily-activity')).toBeVisible()
  await expect(page.getByTestId('analysis-priority-matrix')).toBeVisible()
  await expect(page.getByTestId('analysis-chronology').locator('canvas')).toHaveCount(1)
  expect(consoleErrors).toEqual([])
})

test('timeline filters refresh data and chart selection opens event detail', async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page)
  const selectedEventId = '00000000-0000-0000-0000-000000000099'
  const seenQueries: string[] = []

  await page.route('**/api/v1/events/timeline?**', async (route) => {
    const url = new URL(route.request().url())
    const days = url.searchParams.get('days')
    const reviewStatus = url.searchParams.get('review_status')

    seenQueries.push(`days=${days ?? ''};review_status=${reviewStatus ?? ''}`)

    const entry = {
      event_id: selectedEventId,
      title: reviewStatus === 'approved' ? 'Approved launch window' : 'Needs review launch window',
      category: 'product',
      review_status: reviewStatus ?? 'needs_review',
      source_id: 'slack',
      start: '2026-03-01T10:00:00Z',
      end: '2026-03-07T10:00:00Z',
      importance: 77,
      confidence: 0.91,
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ entries: [entry], total: 1 }),
    })
  })

  await mockInvestigationRoutes(page, selectedEventId)

  await page.goto('/timeline?days=30&reviewStatus=needs_review')

  await expect(page.getByRole('heading', { name: 'Event analysis workspace' })).toBeVisible()
  await page.selectOption('#days-filter', '7')
  await page.selectOption('#timeline-status-filter', 'approved')

  await expect(page).toHaveURL(/days=7/)
  await expect(page).toHaveURL(/reviewStatus=approved/)
  await expect.poll(() => seenQueries).toContain('days=7;review_status=approved')

  const chart = page.getByTestId('analysis-chronology').locator('canvas').first()
  await expect(chart).toBeVisible()

  const box = await chart.boundingBox()
  if (!box) {
    throw new Error('Timeline chart did not render a clickable canvas')
  }

  await chart.click({
    position: {
      x: Math.round(box.width * 0.5),
      y: Math.round(box.height * 0.5),
    },
  })

  await expect(page.getByTestId('event-detail-panel')).toContainText('Approved launch window')
  await expect(page.getByTestId('event-detail-panel')).toContainText('approved')
  await page.getByTestId('event-detail-panel').getByRole('button', { name: 'History' }).click()
  await expect(page.getByTestId('event-audit-list')).toContainText('Promoted after manual verification.')
  expect(consoleErrors).toEqual([])
})

test('review investigation tabs expose source, history, relations, and unmerge', async ({ page }) => {
  const eventId = '00000000-0000-0000-0000-000000000155'
  const consoleErrors = collectConsoleErrors(page)

  await page.route('**/api/v1/events?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [buildMockEvent(eventId, { review_status: 'needs_review', reviewed_by: null, reviewed_at: null })],
        total: 1,
        limit: 200,
        offset: 0,
      }),
    })
  })

  await page.route('**/api/v1/events/stats', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        needs_review: 1,
        approved: 0,
        published: 0,
        rejected: 0,
        archived: 0,
      }),
    })
  })

  await mockInvestigationRoutes(page, eventId, {
    review_status: 'needs_review',
    reviewed_by: null,
    reviewed_at: null,
  })

  await page.route(`**/api/v1/events/${eventId}/unmerge`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        restored_event_ids: ['00000000-0000-0000-0000-000000000188'],
      }),
    })
  })

  await page.goto('/review?status=needs_review')

  await page.getByTestId('events-row').first().click()
  await page.getByLabel('Reviewer name').fill('frontend-smoke')
  const detailPanel = page.getByTestId('event-detail-panel')

  await detailPanel.getByRole('button', { name: 'Source' }).click()
  await expect(page.getByTestId('event-source-context')).toContainText('releases-bot')
  await expect(page.getByRole('link', { name: 'Open Slack permalink' })).toBeVisible()

  await detailPanel.getByRole('button', { name: 'History' }).click()
  await expect(page.getByTestId('event-audit-list')).toContainText('Promoted after manual verification.')

  await detailPanel.getByRole('button', { name: 'Relations' }).click()
  await expect(page.getByTestId('event-relations-list')).toContainText('00000000-0000-0000-0000-000000000188')

  await page.getByRole('button', { name: 'Unmerge absorbed' }).click()
  await expect(page.getByText(/restored 1 absorbed events/i)).toBeVisible()
  expect(consoleErrors).toEqual([])
})

test('live seeded backend shows unmerge on an absorbed relation', async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page)

  await page.goto('/review?status=approved')

  await expect(page.getByRole('heading', { name: 'Review extracted events' })).toBeVisible()

  const targetRow = page.getByTestId('events-row').filter({ hasText: 'API Gateway v2' })
  await expect(targetRow).toHaveCount(1)
  await targetRow.click()

  const detailPanel = page.getByTestId('event-detail-panel')
  await expect(detailPanel).toContainText('API Gateway v2')
  await detailPanel.getByRole('button', { name: 'Relations' }).click()
  await expect(page.getByTestId('event-relations-list')).toContainText('00000000-0000-0000-0000-000000000009')

  await page.getByLabel('Reviewer name').fill('frontend-smoke')
  await page.getByRole('button', { name: 'Unmerge absorbed' }).click()

  await expect(page.getByText(/restored 1 absorbed events/i)).toBeVisible()
  await expect(page.getByText('No related events are attached to this event.')).toBeVisible()
  expect(consoleErrors).toEqual([])
})

test('review actions send the note field to backend mutations', async ({ page }) => {
  const eventId = '00000000-0000-0000-0000-000000000166'
  let capturedNote: string | undefined

  await page.route('**/api/v1/events?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [buildMockEvent(eventId, { review_status: 'needs_review', reviewed_by: null, reviewed_at: null })],
        total: 1,
        limit: 200,
        offset: 0,
      }),
    })
  })

  await page.route('**/api/v1/events/stats', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        needs_review: 1,
        approved: 0,
        published: 0,
        rejected: 0,
        archived: 0,
      }),
    })
  })

  await mockInvestigationRoutes(page, eventId, {
    review_status: 'needs_review',
    reviewed_by: null,
    reviewed_at: null,
  })

  await page.route(`**/api/v1/events/${eventId}/review`, async (route) => {
    const payload = route.request().postDataJSON() as { note?: string }
    capturedNote = payload.note

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success' }),
    })
  })

  await page.goto('/review?status=needs_review')
  await page.getByTestId('events-row').first().click()
  await page.getByLabel('Reviewer name').fill('frontend-smoke')
  await page.getByLabel('Review note').fill('Rejecting because source context is incomplete.')
  await page.getByTestId('review-action-bar').getByRole('button', { name: 'Reject' }).click()

  await expect(page.getByText(/reject completed/i)).toBeVisible()
  expect(capturedNote).toBe('Rejecting because source context is incomplete.')
})

test('editing from analysis view refetches timeline data immediately', async ({ page }) => {
  const eventId = '00000000-0000-0000-0000-000000000177'
  let currentTitle = 'Original analysis title'
  let timelineRequestCount = 0

  await page.route('**/api/v1/events/timeline?**', async (route) => {
    timelineRequestCount += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        entries: [
          {
            event_id: eventId,
            title: currentTitle,
            category: 'product',
            review_status: 'approved',
            source_id: 'slack',
            start: '2026-03-01T10:00:00Z',
            end: '2026-03-07T10:00:00Z',
            importance: 77,
            confidence: 0.91,
          },
        ],
        total: 1,
      }),
    })
  })

  await page.route(`**/api/v1/events/${eventId}`, async (route) => {
    if (route.request().method() === 'PATCH') {
      const payload = route.request().postDataJSON() as { updates?: { title?: string } }
      currentTitle = payload.updates?.title ?? currentTitle
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildMockEvent(eventId, { title: currentTitle })),
    })
  })

  for (const endpoint of ['audit', 'versions', 'relations']) {
    await page.route(`**/api/v1/events/${eventId}/${endpoint}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    })
  }

  await page.route(`**/api/v1/events/${eventId}/message-metadata`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        permalink: null,
        post_url: null,
        forwarded_from: null,
        reply_count: 0,
        reactions_count: 0,
        has_file: false,
        file_mime: null,
      }),
    })
  })

  await page.addInitScript(() => {
    window.localStorage.setItem('review-actor', 'frontend-smoke')
  })

  await page.goto('/timeline?days=30&reviewStatus=approved')

  const chart = page.getByTestId('analysis-chronology').locator('canvas').first()
  const box = await chart.boundingBox()
  if (!box) {
    throw new Error('Analysis chronology did not render a clickable canvas')
  }

  await chart.click({
    position: {
      x: Math.round(box.width * 0.5),
      y: Math.round(box.height * 0.5),
    },
  })

  const detailPanel = page.getByTestId('event-detail-panel')
  await detailPanel.getByRole('button', { name: 'Edit fields' }).click()
  await page.getByLabel('Title').fill('Updated analysis title')
  await page.getByRole('button', { name: 'Save changes' }).click()

  await expect(detailPanel).toContainText('Updated analysis title')
  await expect.poll(() => timelineRequestCount).toBeGreaterThan(1)
})

test('review page shows empty state when events endpoint returns no items', async ({ page }) => {
  await page.route('**/api/v1/events?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, limit: 200, offset: 0 }),
    })
  })

  await page.goto('/review?status=needs_review')
  await expect(page.getByText('No events in this queue')).toBeVisible()
})

test('review page shows error state when events request fails', async ({ page }) => {
  await page.route('**/api/v1/events?**', async (route) => {
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'boom' }),
    })
  })

  await page.goto('/review?status=needs_review')
  await expect(page.getByText('Could not load review data')).toBeVisible()
})
