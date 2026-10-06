import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Every page loads through a session check plus page fetches in a jsdom that's slow under
// parallel load; the 1 s findBy/waitFor default is the main source of flakes. Pass-fast, fail-slow.
configure({ asyncUtilTimeout: 10000 })

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
