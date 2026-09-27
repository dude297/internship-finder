import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  detail,
  feedRecord,
  listPage,
  loggedIn,
  mockApi,
  renderAt,
  source,
  summary,
} from './helpers'

// Synthetic imported opportunities only.

const imported = (changes: Record<string, unknown> = {}) =>
  summary({
    origin: 'imported',
    availability: 'open',
    source_names: ['Tech Internship Discovery Feed'],
    posted_at: '2040-09-20T00:00:00Z',
    requirements_assessment_status: 'unassessed',
    eligibility_status: 'needs_verification',
    ...changes,
  })

function listQuery(path: string): URLSearchParams {
  return new URLSearchParams(path.split('?')[1])
}

describe('discovery list', () => {
  it('labels imported, closed, and manual opportunities', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/opportunities': () =>
        listPage([
          imported({ id: 'a', title: 'Open Import' }),
          imported({
            id: 'b',
            title: 'Closed Import',
            availability: 'closed',
            posted_at: null,
            application_status: 'applied',
          }),
          summary({ id: 'c', title: 'Manual One' }),
        ]),
    })
    renderAt('/opportunities')

    const [open, closed, manual] = await screen.findAllByRole('listitem')
    expect(within(open).getByText('Imported')).toBeInTheDocument()
    expect(within(open).getByText('Tech Internship Discovery Feed')).toBeInTheDocument()
    expect(within(open).getByText(/^Posted /)).toBeInTheDocument()
    expect(within(open).getByText('Unassessed')).toBeInTheDocument()
    expect(within(open).queryByText('Closed')).not.toBeInTheDocument()
    expect(within(closed).getByText('Closed')).toBeInTheDocument()
    expect(within(closed).getByText(/^Found /)).toBeInTheDocument()
    expect(within(closed).getByText('Applied')).toBeInTheDocument()
    expect(within(manual).getByText('Manual')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Showing 1–3 of 3')
  })

  it('requests one bounded page and pages through the rest', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [],
      'GET /api/opportunities': (call) => {
        const offset = Number(listQuery(call.path).get('offset'))
        return listPage([imported({ id: `o${offset}`, title: `Item at ${offset}` })], {
          total: 120,
          offset,
        })
      },
    })
    renderAt('/opportunities')

    expect(await screen.findByText('Item at 0')).toBeInTheDocument()
    const first = listQuery(
      calls.find((c) => c.path.startsWith('/api/opportunities'))!.path,
    )
    expect(first.get('limit')).toBe('50')
    expect(first.get('availability')).toBe('open')
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Item at 50')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
    expect(await screen.findByText('Item at 0')).toBeInTheDocument()
  })

  it('sends filters to the server and resets to the first page', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/opportunities': () => listPage([]),
    })
    renderAt('/opportunities?offset=50')
    await screen.findByText(/No opportunities/)

    fireEvent.change(screen.getByLabelText('Search title or organization'), {
      target: { value: ' quantum ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(listQuery(calls.at(-1)!.path).get('q')).toBe('quantum'))
    expect(listQuery(calls.at(-1)!.path).get('offset')).toBe('0')

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'closed' } })
    fireEvent.change(await screen.findByLabelText('Source'), {
      target: { value: 'src-feed' },
    })
    fireEvent.change(screen.getByLabelText('Eligibility'), {
      target: { value: 'needs_verification' },
    })
    fireEvent.change(screen.getByLabelText('Application'), {
      target: { value: 'tracked' },
    })
    fireEvent.change(screen.getByLabelText('Work mode'), { target: { value: 'remote' } })

    await waitFor(() =>
      expect(Object.fromEntries(listQuery(calls.at(-1)!.path))).toEqual({
        limit: '50',
        offset: '0',
        q: 'quantum',
        availability: 'closed',
        source: 'src-feed',
        eligibility: 'needs_verification',
        application_status: 'tracked',
        remote_mode: 'remote',
      }),
    )
    expect(screen.getByText('No opportunities match these filters.')).toBeInTheDocument()
  })
})

describe('imported opportunity detail', () => {
  it('asks for a requirement review and shows provenance', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({
          origin: 'imported',
          availability: 'open',
          manually_curated_at: null,
          requirements_assessment_status: 'unassessed',
          requirements: [],
          posted_at: '2040-09-20T00:00:00Z',
          sources: [feedRecord()],
        }),
    })
    renderAt('/opportunities/opp-1')

    const review = await screen.findByRole('link', { name: 'Review requirements' })
    expect(review).toHaveAttribute('href', '/opportunities/opp-1/edit')
    expect(screen.getByText(/never assessed automatically/)).toBeInTheDocument()

    const provenance = screen.getByRole('region', { name: 'Source' })
    expect(
      within(provenance).getByText('Tech Internship Discovery Feed'),
    ).toBeInTheDocument()
    expect(within(provenance).getByText('Active')).toBeInTheDocument()
    expect(
      within(provenance).getByRole('link', { name: 'Original posting' }),
    ).toHaveAttribute('href', 'https://careers.example.com/jobs/synthetic-1')
    expect(within(provenance).queryByText(/raw/i)).not.toBeInTheDocument()
  })

  it('shows a closed posting with its kept tracking and curated edits', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({
          origin: 'imported',
          availability: 'closed',
          sources: [feedRecord({ is_active: false, closed_at: '2040-10-05T12:00:00Z' })],
          application: {
            status: 'applied',
            submitted_on: '2040-10-02',
            notes: 'Synthetic note.',
            created_at: '2040-10-02T12:00:00Z',
            updated_at: '2040-10-02T12:00:00Z',
          },
        }),
    })
    renderAt('/opportunities/opp-1')

    expect(
      await screen.findByText(/Closed: no source lists this posting/),
    ).toBeInTheDocument()
    const provenance = screen.getByRole('region', { name: 'Source' })
    expect(within(provenance).getByText(/Closed Oct/)).toBeInTheDocument()
    expect(within(provenance).getByText(/are kept when sources sync/)).toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: 'Review requirements' }),
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText('Private notes')).toHaveValue('Synthetic note.')
  })

  it('explains in the editor that a review survives later syncs', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({ origin: 'imported', availability: 'open', sources: [feedRecord()] }),
    })
    renderAt('/opportunities/opp-1/edit')

    expect(await screen.findByText(/later syncs keep your edits/)).toBeInTheDocument()
  })
})
