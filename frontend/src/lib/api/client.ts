import { env } from '../env'

type QueryValue = string | number | boolean | undefined

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  query?: Record<string, QueryValue>,
): Promise<T> {
  const url = new URL(`${env.apiBaseUrl}${path}`)

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== '') {
        url.searchParams.set(key, String(value))
      }
    }
  }

  const defaultHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (env.reviewApiToken) {
    defaultHeaders['X-Review-Api-Token'] = env.reviewApiToken
  }

  const response = await fetch(url, {
    ...init,
    headers: {
      ...defaultHeaders,
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null
    throw new ApiError(response.status, payload?.detail ?? 'Request failed')
  }

  return (await response.json()) as T
}

export const apiClient = {
  get: <T>(path: string, query?: Record<string, QueryValue>) =>
    request<T>(path, undefined, query),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
}
