import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { listPage, loggedIn, mockApi, renderAt, summary } from './helpers'

// Synthetic fixtures only.
const dataAge = (changes: Record<string, unknown> = {}) => ({
  last_successful_sync_at: '2041-03-08T00:00:00Z',
  age_hours: 50,
  stale: true,
  reason: 'stale',
  ...changes,
})

describe('data age banner', () => {
  it('shows the paused-sync warning with a link to Sources when stale', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/status/freshness': () => dataAge(),
      'GET /api/sources': () => [],
    })
    renderAt('/sources')
    const banner = (await screen.findByText(/Sources last synced/)).closest('div')!
    expect(banner).toHaveTextContent('Sources last synced 2 days ago')
    expect(banner).toHaveTextContent('scheduled sync may be paused')
    expect(screen.getByRole('link', { name: 'Check the Sources page' })).toHaveAttribute(
      'href',
      '/sources',
    )
  })

  it('renders nothing when data is fresh', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/status/freshness': () =>
        dataAge({ stale: false, age_hours: 3, reason: 'ok' }),
      'GET /api/sources': () => [],
    })
    renderAt('/sources')
    await waitFor(() =>
      expect(calls.some((c) => c.path === '/api/status/freshness')).toBe(true),
    )
    expect(screen.queryByText(/scheduled sync may be paused/)).not.toBeInTheDocument()
  })
})

describe('posted filter', () => {
  it('sends posted_within', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [],
      'GET /api/opportunities': () => listPage([summary()]),
    })
    renderAt('/opportunities')
    await screen.findByText('Example Summer Research Program')
    fireEvent.change(screen.getByLabelText('Posted'), { target: { value: '30' } })
    await waitFor(() => {
      const last = calls.filter((c) => c.path.startsWith('/api/opportunities?')).at(-1)!
      expect(new URLSearchParams(last.path.split('?')[1]).get('posted_within')).toBe('30')
    })
  })
})
