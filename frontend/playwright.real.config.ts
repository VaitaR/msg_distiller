import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'real-data.spec.ts',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report-real', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:4174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: [
    {
      command:
        'cd .. && SLACK_BOT_TOKEN=test-token OPENAI_API_KEY=test-key REVIEW_API_TOKEN=test-review-token DB_PATH=data/slack_events.db .venv/bin/python scripts/run_api_server.py --host 127.0.0.1 --port 18001',
      url: 'http://127.0.0.1:18001/api/v1/health',
      reuseExistingServer: false,
    },
    {
      command:
        'VITE_API_BASE_URL=http://127.0.0.1:18001 VITE_REVIEW_API_TOKEN=test-review-token npm run dev -- --host 127.0.0.1 --port 4174',
      url: 'http://127.0.0.1:4174',
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
