import { defineConfig } from '@playwright/test'

// `make e2e` (= `pnpm exec playwright test`): the demo flow in frontend/e2e against the MSW mocks, recorded as video
// (the demo fallback). A dedicated port with --strictPort, so a presenter's non-mock `pnpm dev` on 5173 is never
// mistaken for the mock server. E2E_SLOWMO=<ms> slows every action down for a recording people can follow.
// E2E_BASE_URL=<url> points the same spec at a running app with a live backend instead (project `live`, no web server
// is started; backend on the demo-start scenario). Not rehearsed yet: several steps assert mock-mode behaviour, see the
// comments in e2e/demo-flow.spec.ts.
const PORT = Number(process.env.E2E_PORT ?? 5199)
const liveUrl = process.env.E2E_BASE_URL

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  // The whole demo is one test (the mock state lives in the page, a reload resets it), so the budget is generous.
  timeout: 180_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    // Full Chromium in new headless mode instead of the separate headless shell (crashed on WSL2 in testing).
    channel: 'chromium',
    baseURL: liveUrl ?? `http://localhost:${PORT}`,
    locale: 'cs-CZ',
    timezoneId: 'Europe/Prague',
    viewport: { width: 1440, height: 900 },
    video: { mode: 'on', size: { width: 1440, height: 900 } },
    trace: 'retain-on-failure',
    acceptDownloads: true,
    launchOptions: { slowMo: Number(process.env.E2E_SLOWMO ?? 0) },
  },
  projects: [{ name: liveUrl ? 'live' : 'mock' }],
  webServer: liveUrl
    ? undefined
    : {
        command: `pnpm dev --port ${PORT} --strictPort`,
        url: `http://localhost:${PORT}`,
        env: { VITE_MOCKS: '1' },
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
})
