import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testIgnore: 'real-data.spec.ts',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: true,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: [
    {
      command:
        'SLACK_BOT_TOKEN=test-token OPENAI_API_KEY=test-key REVIEW_API_TOKEN=test-review-token ../.venv/bin/python e2e/run_seeded_api_server.py --port 18000',
      url: 'http://127.0.0.1:18000/api/v1/health',
      reuseExistingServer: false,
    },
    {
      command:
        'VITE_API_BASE_URL=http://127.0.0.1:18000 VITE_REVIEW_API_TOKEN=test-review-token npm run dev -- --host 127.0.0.1 --port 4173',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: false,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})