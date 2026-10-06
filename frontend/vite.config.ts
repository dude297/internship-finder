import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The browser only ever talks to this origin; /api is proxied to FastAPI so the session cookie
// is same-origin (ADR-007 §6). A hosted deployment must keep an equivalent same-origin setup.
const api = { '/api': 'http://localhost:8000' }

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: api },
  preview: { proxy: api },
  test: {
    environment: 'jsdom',
    testTimeout: 20000, // secondary to the 5 s asyncUtilTimeout in tests/setup.ts
    hookTimeout: 20000,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
  },
})
