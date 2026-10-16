import { defineConfig } from '@playwright/test'

// Config only: tests live in frontend/e2e (owned by P4).
export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://localhost:5173', locale: 'cs-CZ', timezoneId: 'Europe/Prague', video: 'on' },
  webServer: {
    command: 'VITE_MOCKS=1 pnpm dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
  },
})
