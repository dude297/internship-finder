import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { formatDays, formatRate, shares } from '../src/lib/dashboard'
import {
  dashboard,
  empty,
  loggedIn,
  mockApi,
  renderAt,
  zeroPipeline as zero,
} from './helpers'

// Synthetic data only.

describe('dashboard helpers', () => {
  it('never renders NaN, Infinity, or a fake zero for missing data', () => {
    expect(formatRate(null)).toBe('Not enough data yet')
    expect(formatRate(Number.NaN)).toBe('Not enough data yet')
    expect(formatRate(0.5)).toBe('50%')
    expect(formatRate(0)).toBe('0%')
    expect(formatDays(null)).toBe('Not enough data yet')
    expect(formatDays(Number.POSITIVE_INFINITY)).toBe('Not enough data yet')
    expect(formatDays(4)).toBe('4.0 days')
    expect(shares([0, 0, 0])).toEqual([0, 0, 0])
    expect(shares([1, 3])).toEqual([25, 75])
  })
})

describe('dashboard page', () => {
  it('is the default authenticated route', async () => {
    mockApi({ ...loggedIn, 'GET /api/dashboard': () => dashboard() })
    renderAt('/anything-unknown')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(
      /Hello|Good (morning|afternoon|evening)/,
    )
    const nav = within(screen.getByRole('navigation', { name: 'Main' }))
    expect(nav.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
    expect(nav.getByRole('link', { name: 'Applications' })).toBeInTheDocument()
  })

  it('renders empty data without NaN or Infinity and with no-data wording', async () => {
    mockApi({ ...loggedIn, 'GET /api/dashboard': () => dashboard() })
    const { container } = renderAt('/dashboard')

    expect(
      await screen.findByText('Nothing needs your attention right now.'),
    ).toBeVisible()
    expect(screen.getByText(/No applications tracked yet/)).toBeInTheDocument()
    expect(screen.getAllByText('Not enough data yet').length).toBe(6)
    expect(container.textContent).not.toMatch(/NaN|Infinity|undefined/)
    const funnel = screen.getByRole('region', { name: 'Outcomes' })
    expect(within(funnel).queryByText('0%')).not.toBeInTheDocument()
  })

  it('shows actions with their kind, pipeline counts, and health links', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/dashboard': () =>
        dashboard({
          actions: {
            closing_soon: empty,
            pending_requirement_review: {
              total: 1,
              items: [
                {
                  id: 'opp-2',
                  title: 'Review Me',
                  organization: 'Example Org',
                  reason: '2 suggested requirements to review',
                  date: null,
                  kind: null,
                },
              ],
            },
            applications: {
              total: 1,
              items: [
                {
                  id: 'opp-1',
                  title: 'Example Internship',
                  organization: 'Example Org',
                  reason: 'Email recruiter (due 2041-03-08)',
                  date: '2041-03-08',
                  kind: 'follow_up_overdue',
                },
              ],
            },
            total: 2,
          },
          pipeline: { ...zero, applied: 3, interview: 1 },
          funnel: {
            ...dashboard().funnel,
            applied: 6,
            interviewed: 2,
            applied_to_interview_rate: 0.333,
            median_days_to_interview: 4.5,
          },
        }),
    })
    renderAt('/dashboard')

    const actions = await screen.findByRole('region', { name: /Action required \(2\)/ })
    expect(within(actions).getByText('Overdue')).toBeInTheDocument()
    expect(
      within(actions).getByRole('link', { name: 'Example Internship' }),
    ).toHaveAttribute('href', '/opportunities/opp-1')
    // Suggestions, not problems.
    expect(
      within(actions).getByText(/Suggested requirements awaiting/),
    ).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/problem/i)

    const pipeline = screen.getByRole('region', { name: 'Application pipeline' })
    expect(within(pipeline).getByRole('link', { name: 'Applied' })).toHaveAttribute(
      'href',
      '/applications?stage=applied',
    )
    expect(within(pipeline).getByText(/4 tracked/)).toBeInTheDocument()

    const discovery = screen.getByRole('region', { name: 'Discovery health' })
    expect(within(discovery).getByRole('link', { name: 'Sources' })).toHaveAttribute(
      'href',
      '/sources',
    )
    expect(screen.getByRole('link', { name: 'Review requirements' })).toHaveAttribute(
      'href',
      '/requirements',
    )
    const funnel = screen.getByRole('region', { name: 'Outcomes' })
    expect(within(funnel).getByText('33%')).toBeInTheDocument()
    expect(within(funnel).getByText('4.5 days')).toBeInTheDocument()
  })

  it('shows an error instead of a blank page when the request fails', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/dashboard': () => new Response('{"detail":"boom"}', { status: 500 }),
    })
    renderAt('/dashboard')
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})

describe('applications page', () => {
  const item = (over = {}) => ({
    id: 'app-1',
    opportunity_id: 'opp-1',
    title: 'Example Internship',
    organization: 'Example Org',
    application_url: 'https://example.org/apply',
    application_deadline: null,
    status: 'applied',
    next_action: 'Email recruiter',
    next_action_due: '2041-03-08',
    interview_at: null,
    applied_at: '2041-03-01T12:00:00Z',
    updated_at: '2041-03-01T12:00:00Z',
    created_at: '2041-03-01T12:00:00Z',
    follow_up_overdue: true,
    ...over,
  })
  const page = (items: unknown[]) => ({ today: '2041-03-10', total: items.length, items })

  it('lists applications, flags overdue follow-ups, and changes stage with a select', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/applications': () => page([item()]),
      'PUT /api/opportunities/opp-1/application': () => ({
        ...item({ status: 'interview' }),
        notes: null,
        submitted_on: null,
      }),
    })
    renderAt('/applications')

    expect(await screen.findByText(/due 2041-03-08 \(overdue\)/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open application link' })).toHaveAttribute(
      'href',
      'https://example.org/apply',
    )
    fireEvent.change(screen.getByLabelText('Stage for Example Internship'), {
      target: { value: 'interview' },
    })
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({
        status: 'interview',
      }),
    )
  })

  it('quick action marks an application applied with a status-only patch', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/applications': () => page([item({ status: 'applying' })]),
      'PUT /api/opportunities/opp-1/application': () => ({}),
    })
    renderAt('/applications')
    fireEvent.click(await screen.findByRole('button', { name: 'Mark applied' }))
    await waitFor(() =>
      expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ status: 'applied' }),
    )
  })

  it('pipeline view groups outcomes in one column and shows an empty state', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/applications': () =>
        page([
          item({ status: 'rejected', follow_up_overdue: false }),
          item({
            id: 'app-2',
            opportunity_id: 'opp-2',
            title: 'Second',
            status: 'saved',
          }),
        ]),
    })
    renderAt('/applications')
    fireEvent.click(await screen.findByRole('tab', { name: 'Pipeline' }))
    const outcome = await screen.findByRole('region', { name: 'Outcome column' })
    expect(within(outcome).getByText('Example Internship')).toBeInTheDocument()
    expect(
      within(screen.getByRole('region', { name: 'Offer column' })).getByText('None'),
    ).toBeInTheDocument()
  })

  it('shows an empty state with no applications', async () => {
    mockApi({ ...loggedIn, 'GET /api/applications': () => page([]) })
    renderAt('/applications')
    expect(await screen.findByText(/No applications match/)).toBeInTheDocument()
  })
})
