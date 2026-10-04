import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  coverageMetrics,
  discoveryResponse,
  json,
  loggedIn,
  mockApi,
  providerCount,
  renderAt,
  run,
  source,
  suggestion,
} from './helpers'

// Synthetic discovery coverage and suggestions only.

describe('source coverage', () => {
  it('renders coverage metrics and the provider breakdown', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () =>
        discoveryResponse({
          coverage: coverageMetrics({ active_opportunities: 123, with_description: 50 }),
          providers: [providerCount({ provider: 'workday', supported: false })],
        }),
    })
    renderAt('/sources')

    expect(
      await screen.findByRole('heading', { name: 'Source Coverage' }),
    ).toBeInTheDocument()
    expect(screen.getByText('123')).toBeInTheDocument()
    expect(screen.getByText('Workday')).toBeInTheDocument()
    expect(screen.getByText('No')).toBeInTheDocument()
  })

  it('renders suggestions with an already-configured one disabled', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () =>
        discoveryResponse({
          suggestions: [
            suggestion(),
            suggestion({
              kind: 'lever',
              identifier: 'exampleinstitute',
              region: 'eu',
              key: 'lever:eu:exampleinstitute',
              suggested_display_name: 'Example Institute',
              display_name_ambiguous: true,
              already_configured: true,
            }),
          ],
        }),
    })
    renderAt('/sources')

    expect(
      await screen.findByRole('heading', { name: 'Suggested Sources' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Example Robotics')).toBeInTheDocument()
    expect(screen.getByText(/ambiguous name/)).toBeInTheDocument()
    expect(screen.getByText('EU')).toBeInTheDocument()
    expect(screen.getByText('Configured')).toBeInTheDocument()

    const configuredCheckbox = screen.getByLabelText('Select lever:eu:exampleinstitute')
    expect(configuredCheckbox).toBeDisabled()
    expect(configuredCheckbox).not.toBeChecked()
  })

  it('shows the empty state when discovery has no suggestions', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () => discoveryResponse({ suggestions: [] }),
    })
    renderAt('/sources')

    expect(
      await screen.findByText('No supported sources found in the discovery feed.'),
    ).toBeInTheDocument()
  })

  it('selects, caps select-all at 25, and tracks the counter', async () => {
    const many = Array.from({ length: 30 }, (_, i) =>
      suggestion({ key: `greenhouse:board-${i}`, identifier: `board-${i}` }),
    )
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () => discoveryResponse({ suggestions: many }),
    })
    renderAt('/sources')

    await screen.findByText('0 selected (max 25)')
    fireEvent.click(screen.getByLabelText('Select all unconfigured suggestions'))
    expect(await screen.findByText('25 selected (max 25)')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Add selected sources' }),
    ).not.toBeDisabled()

    // Checking one more past the cap disables Add.
    fireEvent.click(screen.getByLabelText('Select greenhouse:board-29'))
    expect(await screen.findByText('26 selected (max 25)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add selected sources' })).toBeDisabled()
  })

  it('sends only kind, identifier, and region per selection, then refreshes', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () => discoveryResponse(),
      'POST /api/sources/discovery/add': () => ({
        created: [
          source({ id: 'src-gh', kind: 'greenhouse', display_name: 'Example Robotics' }),
        ],
        skipped: [],
      }),
    })
    renderAt('/sources')

    fireEvent.click(await screen.findByLabelText('Select greenhouse:examplerobotics'))
    fireEvent.click(screen.getByRole('button', { name: 'Add selected sources' }))

    expect(await screen.findByText(/Added 1, skipped 0/)).toBeInTheDocument()
    expect(screen.getByText(/Use Sync on the new sources/)).toBeInTheDocument()

    const add = calls.find((c) => c.path === '/api/sources/discovery/add')!
    expect(add.body).toEqual({
      sources: [{ kind: 'greenhouse', identifier: 'examplerobotics', region: null }],
    })
    // Discovery and the sources list are both refetched.
    expect(calls.filter((c) => c.path === '/api/sources/discovery')).toHaveLength(2)
    expect(calls.filter((c) => c.path === '/api/sources')).toHaveLength(2)
    // Selection clears after a successful add.
    await waitFor(() =>
      expect(screen.getByText('0 selected (max 25)')).toBeInTheDocument(),
    )
  })

  it('reloads coverage and suggestions after a sync', async () => {
    let discoveryCalls = 0
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () =>
        ++discoveryCalls === 1
          ? discoveryResponse({ suggestions: [] })
          : discoveryResponse(),
      'POST /api/sources/src-feed/sync': () => run(),
    })
    renderAt('/sources')

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Sync Tech Internship Discovery Feed now',
      }),
    )

    expect(
      await screen.findByLabelText('Select greenhouse:examplerobotics'),
    ).toBeInTheDocument()
    expect(discoveryCalls).toBe(2)
  })

  it('shows a 422 error from the add endpoint', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () => discoveryResponse(),
      'POST /api/sources/discovery/add': () =>
        json({ detail: 'One or more sources is no longer a valid suggestion.' }, 422),
    })
    renderAt('/sources')

    fireEvent.click(await screen.findByLabelText('Select greenhouse:examplerobotics'))
    fireEvent.click(screen.getByRole('button', { name: 'Add selected sources' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'One or more sources is no longer a valid suggestion.',
    )
  })
})
