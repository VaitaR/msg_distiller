import { expect, test } from '@playwright/test'

function collectConsoleErrors(page: Parameters<typeof test>[0]['page']) {
  const consoleErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })

  return consoleErrors
}

test('real data review queue loads and opens an investigation panel', async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page)

  await page.goto('/review?status=needs_review')

  await expect(page.getByRole('heading', { name: 'Review extracted events' })).toBeVisible()

  const rows = page.getByTestId('events-row')
  await expect(rows.first()).toBeVisible()
  expect(await rows.count()).toBeGreaterThan(0)

  await rows.first().click()

  const detailPanel = page.getByTestId('event-detail-panel')
  await expect(detailPanel).toBeVisible()
  await detailPanel.getByRole('button', { name: 'Source' }).click()
  await expect(page.getByTestId('event-source-context')).toBeVisible()
  expect(consoleErrors).toEqual([])
})

test('real data analysis workspace renders charts for the local snapshot', async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page)

  await page.goto('/timeline?days=90')

  await expect(page.getByRole('heading', { name: 'Event analysis workspace' })).toBeVisible()
  await expect(page.getByTestId('analysis-dashboard')).toBeVisible()
  await expect(page.getByTestId('analysis-daily-activity')).toBeVisible()
  await expect(page.getByTestId('analysis-chronology').locator('canvas')).toHaveCount(1)
  await expect(page.getByText('No events in this time window')).toHaveCount(0)
  expect(consoleErrors).toEqual([])
})
