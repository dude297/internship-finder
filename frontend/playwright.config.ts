import { defineConfig, devices } from '@playwright/test'
import { backendDir, e2eDatabaseUrl, ingestionFixtureFile, python } from './e2e/env.ts'

// Runs the real stack: FastAPI on :8000, Vite on :5173 proxying /api, and Chromium.
// Needs E2E_DATABASE_URL (a disposable PostgreSQL database). All data is synthetic.
export default defineConfig({
  testDir: 'e2e',
  globalSetup: './e2e/global-setup.ts',
  workers: 1,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --port 8000`,
      cwd: backendDir,
      url: 'http://localhost:8000/api/health',
      env: {
        ...process.env,
        DATABASE_URL: e2eDatabaseUrl(),
        // Ingestion reads synthetic responses from this file; it never touches the network.
        INGESTION_FIXTURE_FILE: ingestionFixtureFile,
      } as Record<string, string>,
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --port 5173 --strictPort',
      url: 'http://localhost:5173',
      reuseExistingServer: false,
    },
  ],
})
