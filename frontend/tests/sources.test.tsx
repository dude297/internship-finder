import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  discoveryResponse,
  json,
  loggedIn,
  mockApi,
  renderAt,
  run,
  source,
} from './helpers'

// Synthetic sources and runs only.

const greenhouse = source({
  id: 'src-gh',
  kind: 'greenhouse',
  key: 'greenhouse:examplerobotics',
  identifier: 'examplerobotics',
  display_name: 'Example Robotics',
  scope: 'internships_only',
  builtin: false,
})

describe('sources page', () => {
  it('lists the built-in feed with its latest run, reachable from the navigation', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [
        source({
          last_attempted_at: '2040-10-01T12:00:00Z',
          last_success_at: '2040-10-01T12:00:00Z',
          latest_run: run(),
        }),
      ],
      'GET /api/opportunities': () => ({ items: [], total: 0, limit: 50, offset: 0 }),
    })
    renderAt('/opportunities')
    fireEvent.click(await screen.findByRole('link', { name: 'Sources' }))

    const item = await screen.findByRole('listitem')
    expect(within(item).getByText('Tech Internship Discovery Feed')).toBeInTheDocument()
    expect(within(item).getByText('Discovery feed (built in)')).toBeInTheDocument()
    expect(within(item).getByText('Succeeded')).toBeInTheDocument()
    expect(within(item).getByText('Merged with another source:')).toBeInTheDocument()
    expect(within(item).getByText(/4\.0 s/)).toBeInTheDocument()
    expect(screen.getByText(/Nothing syncs on a schedule/)).toBeInTheDocument()
  })

  it('syncs one source with the CSRF header and shows the result', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [source()],
      'POST /api/sources/src-feed/sync': () =>
        run({
          status: 'partial',
          invalid_count: 1,
          errors: [
            {
              external_id: 'synthetic-9',
              stage: 'normalize',
              code: 'invalid_item',
              message: 'title: Field required',
            },
          ],
        }),
    })
    renderAt('/sources')

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Sync Tech Internship Discovery Feed now',
      }),
    )

    expect(await screen.findByText('Partly succeeded')).toBeInTheDocument()
    expect(screen.getByText(/weren't marked closed/)).toBeInTheDocument()
    expect(screen.getByText('title: Field required')).toBeInTheDocument()
    const sync = calls.find((c) => c.method === 'POST')!
    expect(sync.headers['X-CSRF-Token']).toBe('synthetic-csrf')
  })

  it('shows a failed run without counts', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [
        source({
          latest_run: run({ status: 'failed', error_summary: 'The source timed out.' }),
        }),
      ],
    })
    renderAt('/sources')

    expect(await screen.findByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('The source timed out.')).toBeInTheDocument()
    expect(screen.queryByText('Fetched:')).not.toBeInTheDocument()
  })

  it('syncs all sources', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [source(), greenhouse],
      'POST /api/sources/sync': () => [
        run(),
        run({ id: 'run-2', source_id: 'src-gh', status: 'no_change' }),
      ],
    })
    renderAt('/sources')

    fireEvent.click(await screen.findByRole('button', { name: 'Sync all' }))

    expect(await screen.findByText('Synced 2 sources.')).toBeInTheDocument()
    expect(screen.getByText('No changes')).toBeInTheDocument()
  })

  it('disables a source', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [source()],
      'PUT /api/sources/src-feed': () => source({ enabled: false }),
    })
    renderAt('/sources')

    fireEvent.click(await screen.findByRole('button', { name: 'Disable' }))

    expect(await screen.findByRole('button', { name: 'Enable' })).toBeInTheDocument()
    expect(calls.at(-1)!.body).toEqual({
      display_name: 'Tech Internship Discovery Feed',
      enabled: false,
    })
    expect(
      screen.getByRole('button', { name: 'Sync Tech Internship Discovery Feed now' }),
    ).toBeDisabled()
  })

  it('adds a Greenhouse board from its link', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [source()],
      'POST /api/sources': () => json(greenhouse, 201),
    })
    renderAt('/sources')

    fireEvent.change(await screen.findByLabelText('Organization name'), {
      target: { value: 'Example Robotics' },
    })
    fireEvent.change(screen.getByLabelText('Job board link or name'), {
      target: { value: 'https://job-boards.greenhouse.io/examplerobotics' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add source' }))

    expect(await screen.findByText(/Added Example Robotics/)).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(calls.at(-1)!.body).toEqual({
      kind: 'greenhouse',
      display_name: 'Example Robotics',
      board: 'https://job-boards.greenhouse.io/examplerobotics',
      region: null,
      scope: 'internships_only',
    })
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument()
  })

  it('sends the Lever region only for a bare site name', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [source()],
      'POST /api/sources': () => json(source({ id: 'src-lv', kind: 'lever' }), 201),
    })
    renderAt('/sources')

    fireEvent.change(await screen.findByLabelText('Provider'), {
      target: { value: 'lever' },
    })
    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Example Institute' },
    })
    fireEvent.change(screen.getByLabelText('Job board link or name'), {
      target: { value: 'exampleinstitute' },
    })
    fireEvent.change(screen.getByLabelText('Lever region'), { target: { value: 'eu' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add source' }))

    await waitFor(() => expect(calls.at(-1)!.method).toBe('POST'))
    expect(calls.at(-1)!.body).toMatchObject({ kind: 'lever', region: 'eu' })
  })

  it('shows invalid links on the field and duplicates as an error', async () => {
    let attempt = 0
    mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [source()],
      'POST /api/sources': () =>
        ++attempt === 1
          ? json(
              {
                detail: [
                  {
                    loc: ['body', 'board'],
                    msg: 'Use a Greenhouse board link like https://job-boards.greenhouse.io/<board>',
                    type: 'value_error',
                  },
                ],
              },
              422,
            )
          : json({ detail: 'Example Robotics is already configured.' }, 409),
    })
    renderAt('/sources')

    fireEvent.change(await screen.findByLabelText('Organization name'), {
      target: { value: 'Example Robotics' },
    })
    const board = screen.getByLabelText('Job board link or name')
    fireEvent.change(board, { target: { value: 'https://example.com/board' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add source' }))

    expect(await screen.findByText(/Use a Greenhouse board link/)).toBeInTheDocument()
    expect(board).toHaveAttribute('aria-invalid', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'Add source' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Example Robotics is already configured.',
    )
  })

  it('reports a failed sync request', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [source()],
      'POST /api/sources/src-feed/sync': () =>
        json({ detail: 'Tech Internship Discovery Feed is already syncing.' }, 409),
    })
    renderAt('/sources')

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Sync Tech Internship Discovery Feed now',
      }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('is already syncing.')
  })

  it('reports a load error', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => json({ detail: 'Internal server error.' }, 500),
    })
    renderAt('/sources')

    expect(await screen.findByRole('alert')).toHaveTextContent('Internal server error.')
  })
})
