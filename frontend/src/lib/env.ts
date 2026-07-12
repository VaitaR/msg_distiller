function trimTrailingSlash(value: string) {
  return value.endsWith('/') ? value.slice(0, -1) : value
}

export const env = {
  apiBaseUrl: trimTrailingSlash(
    import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  ),
  reviewApiToken: import.meta.env.VITE_REVIEW_API_TOKEN ?? '',
}
