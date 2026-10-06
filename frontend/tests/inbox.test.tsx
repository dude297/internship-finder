import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { loggedIn, mockApi, renderAt } from './helpers'

// Synthetic data only.

const empty = { total: 0, items: [] }
const item = (over = {}) => ({
  id: 'opp-1',
  title: 'Example Internship',
  organization: 'Example Org',
  reason: 'Application deadline 2041-03-12',
  date: '2041-03-12',
  ...over,
})
const inbox = (over = {}) => ({
  today: '2041-03-10',
  new_high_fit: empty,
  closing_soon: empty,
  pending_requirement_review: empty,
  source_warnings: empty,
  program_verify_by: empty,
  applications: empty,
  ...over,
})

describe('inbox page', () => {
  it('shows an empty state for every section', async () => {
    mockApi({ ...loggedIn, 'GET /api/inbox': () => inbox() })
    renderAt('/inbox')

    expect(await screen.findByRole('heading', { name: 'Inbox' })).toBeInTheDocument()
    expect(screen.getAllByRole('region')).toHaveLength(6)
    expect(screen.getByText('All sources look healthy.')).toBeInTheDocument()
    expect(screen.getByText(/No follow-ups due/)).toBeInTheDocument()
  })

  it('lists items with a link, reason, and an "all" link when more exist', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/inbox': () =>
        inbox({
          closing_soon: { total: 12, items: [item()] },
          source_warnings: {
            total: 1,
            items: [
              item({ id: 'src-1', title: 'Example Board', reason: 'Source stale' }),
            ],
          },
        }),
    })
    renderAt('/inbox')

    const closing = await screen.findByRole('region', { name: /Closing soon/ })
    expect(
      within(closing).getByRole('link', { name: 'Example Internship' }),
    ).toHaveAttribute('href', '/opportunities/opp-1')
    expect(
      within(closing).getByText('Application deadline 2041-03-12'),
    ).toBeInTheDocument()
    expect(
      within(closing).getByRole('link', { name: 'All deadlines (12)' }),
    ).toBeInTheDocument()
    const sources = screen.getByRole('region', { name: /Source warnings/ })
    expect(within(sources).getByRole('link', { name: 'Example Board' })).toHaveAttribute(
      'href',
      '/sources',
    )
  })

  it('shows an error when the inbox fails to load', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/inbox': () =>
        new Response(JSON.stringify({ detail: 'boom' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }),
    })
    renderAt('/inbox')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('is reachable from the main navigation', async () => {
    mockApi({ ...loggedIn, 'GET /api/inbox': () => inbox() })
    renderAt('/inbox')
    expect(await screen.findByRole('link', { name: 'Inbox' })).toHaveAttribute(
      'href',
      '/inbox',
    )
  })
})
