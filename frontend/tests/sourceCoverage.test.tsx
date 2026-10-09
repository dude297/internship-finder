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
    // The coverage section loads after the heading renders: wait for its data.
    expect(await screen.findByText('Workday')).toBeInTheDocument()
    expect(screen.getAllByText('123').length).toBeGreaterThan(0)
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
      await screen.findByText(/No supported sources found in the discovery feed/),
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

  it('summarises coverage and counts enabled direct sources against the cap', async () => {
    const board = (id: string, changes: Record<string, unknown> = {}) =>
      source({
        id,
        kind: 'greenhouse',
        builtin: false,
        identifier: id,
        display_name: id,
        ...changes,
      })
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [
        source(),
        board('alpha'),
        board('beta'),
        board('gamma', { enabled: false }),
      ],
      'GET /api/sources/discovery': () => discoveryResponse(),
    })
    renderAt('/sources')

    const summary = await screen.findByText('Independent discovery')
    expect(summary.closest('div')).toHaveTextContent('30%')
    expect(screen.getByText('Description coverage').closest('div')).toHaveTextContent(
      '40%',
    )
    expect(screen.getByText('Feed-only postings').closest('div')).toHaveTextContent('90')
    // The built-in feed and the disabled board don't count.
    expect(screen.getByText('Direct sources enabled').closest('div')).toHaveTextContent(
      '2 / 100',
    )
  })

  it('orders suggestions by feed-only postings and puts configured ones last', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () =>
        discoveryResponse({
          suggestions: [
            suggestion({
              key: 'greenhouse:small',
              suggested_display_name: 'Small Co',
              feed_only_opportunities: 1,
            }),
            suggestion({
              key: 'greenhouse:done',
              suggested_display_name: 'Done Co',
              feed_only_opportunities: 99,
              already_configured: true,
            }),
            suggestion({
              key: 'greenhouse:big',
              suggested_display_name: 'Big Co',
              feed_only_opportunities: 9,
            }),
          ],
        }),
    })
    renderAt('/sources')

    await screen.findByText('Big Co')
    const names = screen
      .getAllByRole('row')
      .map((row) => row.textContent ?? '')
      .filter((text) => /Co/.test(text))
      .map((text) => /(Big|Small|Done) Co/.exec(text)![1])
    expect(names).toEqual(['Big', 'Small', 'Done'])
  })

  it('groups sources by health, failing first, with the last error', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [
        source({ id: 'ok', display_name: 'Healthy Board', health: 'healthy' }),
        source({
          id: 'bad',
          display_name: 'Broken Board',
          health: 'failing',
          consecutive_failures: 2,
          latest_run: run({
            id: 'run-bad',
            source_id: 'bad',
            status: 'failed',
            error_summary: 'The source timed out.',
          }),
        }),
      ],
      'GET /api/sources/discovery': () => discoveryResponse(),
    })
    renderAt('/sources')

    const failing = await screen.findByRole('heading', { name: /^Failing \(1\)/ })
    const healthy = screen.getByRole('heading', { name: /^Healthy \(1\)/ })
    expect(
      failing.compareDocumentPosition(healthy) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(screen.getByText('Last error:')).toBeInTheDocument()
    // Shown once: the run summary doesn't repeat it.
    expect(screen.getAllByText('The source timed out.')).toHaveLength(1)
    expect(screen.getByText('1 failing, 0 warning, 1 healthy.')).toBeInTheDocument()
  })

  it('says nothing needs attention when no source is failing', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source({ health: 'healthy' })],
      'GET /api/sources/discovery': () => discoveryResponse(),
    })
    renderAt('/sources')

    expect(
      await screen.findByText('Nothing is failing. No source needs attention.'),
    ).toBeInTheDocument()
  })
})
