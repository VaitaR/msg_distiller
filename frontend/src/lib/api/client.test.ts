import { describe, expect, it, vi } from 'vitest'

import { ApiError, apiClient } from './client'

describe('apiClient', () => {
  it('sends query params to the backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await apiClient.get('/api/v1/events', { review_status: 'needs_review', limit: 50 })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [requestUrl, options] = fetchMock.mock.calls[0] as [URL, RequestInit]

    expect(requestUrl.toString()).toBe(
      'http://localhost:8000/api/v1/events?review_status=needs_review&limit=50',
    )
    expect(options).toEqual({ headers: { 'Content-Type': 'application/json' } })
  })

  it('throws ApiError for non-2xx responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'broken' }),
      }),
    )

    await expect(apiClient.get('/api/v1/events')).rejects.toBeInstanceOf(ApiError)
  })
})
