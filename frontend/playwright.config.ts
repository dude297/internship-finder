import { defineConfig, devices } from '@playwright/test'
import { backendDir, e2eDatabaseUrl, python } from './e2e/env.ts'

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
      env: { ...process.env, DATABASE_URL: e2eDatabaseUrl() } as Record<string, string>,
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --port 5173 --strictPort',
      url: 'http://localhost:5173',
      reuseExistingServer: false,
    },
  ],
})
