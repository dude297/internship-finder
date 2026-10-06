import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { detail, json, listPage, loggedIn, mockApi, renderAt, summary } from './helpers'

const noSources = { 'GET /api/sources': () => [] }

describe('opportunity list', () => {
  it('shows an empty state with a way to add one', async () => {
    mockApi({ ...loggedIn, ...noSources, 'GET /api/opportunities': () => listPage([]) })
    renderAt('/opportunities')

    expect(await screen.findByText(/No opportunities yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add opportunity' })).toHaveAttribute(
      'href',
      '/opportunities/new',
    )
  })

  it('keeps every eligibility state distinct', async () => {
    mockApi({
      ...loggedIn,
      ...noSources,
      'GET /api/opportunities': () =>
        listPage([
          summary({ id: 'a', title: 'A', eligibility_status: 'eligible' }),
          summary({
            id: 'b',
            title: 'B',
            eligibility_status: 'needs_verification',
            requirements_assessment_status: 'unassessed',
          }),
          summary({ id: 'c', title: 'C', eligibility_status: 'ineligible' }),
          summary({
            id: 'd',
            title: 'D',
            eligibility_status: null,
            application_status: 'applied',
          }),
        ]),
    })
    renderAt('/opportunities')

    const items = await screen.findAllByRole('listitem')
    expect(within(items[0]).getByText('Eligible')).toBeInTheDocument()
    expect(within(items[1]).getByText('Needs verification')).toBeInTheDocument()
    expect(within(items[1]).queryByText('Eligible')).not.toBeInTheDocument()
    expect(within(items[1]).getByText('Unassessed')).toBeInTheDocument()
    expect(within(items[2]).getByText('Ineligible')).toBeInTheDocument()
    expect(within(items[3]).getByText('Not evaluated')).toBeInTheDocument()
    expect(within(items[3]).getByText('Applied')).toBeInTheDocument()
    expect(
      within(items[0]).getByText('All hard requirements reviewed'),
    ).toBeInTheDocument()
  })

  it('shows an error state', async () => {
    mockApi({
      ...loggedIn,
      ...noSources,
      'GET /api/opportunities': () => json({ detail: 'Internal server error.' }, 500),
    })
    renderAt('/opportunities')

    expect(await screen.findByRole('alert')).toHaveTextContent('Internal server error.')
  })

  it('rejects a malformed response safely', async () => {
    mockApi({
      ...loggedIn,
      ...noSources,
      'GET /api/opportunities': () => listPage([{ id: 1 }]),
    })
    renderAt('/opportunities')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The server sent an unexpected response.',
    )
  })
})

describe('opportunity detail', () => {
  it('explains each rule in plain language', async () => {
    mockApi({ ...loggedIn, 'GET /api/opportunities/opp-1': () => detail() })
    renderAt('/opportunities/opp-1')

    const panel = await screen.findByRole('region', { name: 'Eligibility' })
    expect(within(panel).getAllByText('Needs verification').length).toBeGreaterThan(0)
    expect(
      within(panel).getByText("Citizenship hasn't been entered in your profile."),
    ).toBeInTheDocument()
    expect(within(panel).getByText(/Based on your projected status/)).toHaveTextContent(
      'incoming undergraduate',
    )
    expect(within(panel).getByText('Requirement review')).toBeInTheDocument()
    expect(within(panel).getByText('Rule ELIG-CIT-001 · rules v1')).toBeInTheDocument()
    // The overall result doesn't depend on projection here (citizenship decides it).
    expect(within(panel).queryByRole('note')).not.toBeInTheDocument()
  })

  it('shows the projected-status notice with the relevant dates', async () => {
    const base = detail()
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({
          latest_evaluation: {
            ...base.latest_evaluation,
            eligibility_status: 'eligible',
            depends_on_projected_status: true,
          },
        }),
    })
    renderAt('/opportunities/opp-1')

    const note = await screen.findByRole('note')
    expect(note).toHaveTextContent(
      'This result depends on expected future education dates.',
    )
    expect(note).toHaveTextContent(
      'graduate high_school on 2041-06-10 and enroll on 2041-08-25',
    )
  })

  it('says eligibility needs a profile instead of faking a result', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({ profile_exists: false, latest_evaluation: null }),
    })
    renderAt('/opportunities/opp-1')

    const panel = await screen.findByRole('region', { name: 'Eligibility' })
    expect(within(panel).getByText('Not evaluated')).toBeInTheDocument()
    expect(
      within(panel).getByRole('link', { name: 'fill in your profile' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-evaluate' })).toBeDisabled()
  })

  const noFollowUp = { next_action: null, next_action_due: null, interview_at: null }

  it('tracks the application and changes its status', async () => {
    const application = {
      status: 'saved',
      submitted_on: null,
      notes: null,
      created_at: '2040-10-01T12:00:00Z',
      updated_at: '2040-10-01T12:00:00Z',
    }
    const calls = mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(),
      'PUT /api/opportunities/opp-1/application': ({ body }) => ({
        ...application,
        ...(body as object),
      }),
    })
    renderAt('/opportunities/opp-1')

    fireEvent.click(await screen.findByRole('button', { name: 'Track this opportunity' }))
    const status = await screen.findByLabelText('Status')
    fireEvent.change(status, { target: { value: 'applied' } })
    fireEvent.change(screen.getByLabelText('Submitted on'), {
      target: { value: '2041-01-20' },
    })
    fireEvent.change(screen.getByLabelText('Private notes'), {
      target: { value: 'Synthetic note' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save application' }))

    await screen.findByText('Application tracking saved.')
    const puts = calls.filter((c) => c.method === 'PUT')
    expect(puts.map((c) => c.body)).toEqual([
      { status: 'saved', submitted_on: null, notes: null, ...noFollowUp },
      {
        status: 'applied',
        submitted_on: '2041-01-20',
        notes: 'Synthetic note',
        ...noFollowUp,
      },
    ])
    expect(puts[1].headers['X-CSRF-Token']).toBe('synthetic-csrf')
  })

  it('renders the description as text, never HTML', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({ description: '<img src=x onerror=alert(1)>' }),
    })
    const { container } = renderAt('/opportunities/opp-1')

    expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })
})

describe('manual opportunity form', () => {
  it('builds structured requirements and defaults to unassessed', async () => {
    const calls = mockApi({
      ...loggedIn,
      'POST /api/opportunities': () => detail({ id: 'new-1' }),
      'GET /api/opportunities/new-1': () => detail({ id: 'new-1' }),
    })
    renderAt('/opportunities/new')

    fireEvent.change(await screen.findByLabelText('Title (required)'), {
      target: { value: 'Synthetic Program' },
    })
    fireEvent.change(screen.getByLabelText('Organization (required)'), {
      target: { value: 'Example Org' },
    })
    fireEvent.change(screen.getByLabelText('Start date'), {
      target: { value: '2041-06-20' },
    })
    expect(screen.getByRole('radio', { name: /Unassessed/ })).toBeChecked()

    fireEvent.click(screen.getByRole('button', { name: 'Add requirement' }))
    fireEvent.change(screen.getByLabelText('Minimum age (years)'), {
      target: { value: '16' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Add requirement' }))
    const second = screen.getByRole('group', { name: 'Requirement 2' })
    fireEvent.change(within(second).getByLabelText('Type'), {
      target: { value: 'education' },
    })
    fireEvent.click(within(second).getByLabelText('Undergraduate (college)'))
    fireEvent.click(within(second).getByLabelText(/Incoming students accepted/))
    fireEvent.change(within(second).getByLabelText('Applies'), {
      target: { value: 'explicit_date' },
    })
    fireEvent.change(within(second).getByLabelText('Date'), {
      target: { value: '2041-07-01' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Add requirement' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove requirement 3' }))

    fireEvent.click(screen.getByRole('radio', { name: /All hard requirements reviewed/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save opportunity' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    const post = calls.find((c) => c.method === 'POST')
    expect(post?.body).toMatchObject({
      title: 'Synthetic Program',
      organization: 'Example Org',
      start_date: '2041-06-20',
      application_url: null,
      requirements_assessment_status: 'complete',
      requirements: [
        {
          requirement_type: 'minimum_age',
          value: { years: 16 },
          applies_at: 'program_start',
          reference_date: null,
        },
        {
          requirement_type: 'education',
          value: { levels: ['undergraduate'], accepts_incoming: true },
          applies_at: 'explicit_date',
          reference_date: '2041-07-01',
        },
      ],
    })
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: 'Example Summer Research Program',
      }),
    ).toBeInTheDocument()
  })

  it('shows requirement validation errors from the backend', async () => {
    mockApi({
      ...loggedIn,
      'POST /api/opportunities': () =>
        json(
          {
            detail: [
              {
                loc: ['body', 'requirements', 0],
                msg: 'Value error, reference_date is required exactly when applies_at is explicit_date',
                type: 'value_error',
              },
            ],
          },
          422,
        ),
    })
    renderAt('/opportunities/new')
    fireEvent.change(await screen.findByLabelText('Title (required)'), {
      target: { value: 'Synthetic Program' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save opportunity' }))

    expect(
      await screen.findByText(/Requirement 1: reference_date is required/),
    ).toBeInTheDocument()
  })

  it('loads an existing opportunity for editing', async () => {
    mockApi({ ...loggedIn, 'GET /api/opportunities/opp-1': () => detail() })
    renderAt('/opportunities/opp-1/edit')

    expect(await screen.findByLabelText('Title (required)')).toHaveValue(
      'Example Summer Research Program',
    )
    expect(screen.getByLabelText('Accepted citizenship(s)')).toHaveValue('US')
    expect(
      screen.getByRole('radio', { name: /All hard requirements reviewed/ }),
    ).toBeChecked()
  })
})

describe('volunteer opportunity type', () => {
  it('offers Volunteer in the form and submits opportunity_type volunteer', async () => {
    const calls = mockApi({
      ...loggedIn,
      'POST /api/opportunities': () => detail({ id: 'new-1' }),
      'GET /api/opportunities/new-1': () => detail({ id: 'new-1' }),
    })
    renderAt('/opportunities/new')
    fireEvent.change(await screen.findByLabelText('Title (required)'), {
      target: { value: 'Synthetic Food Drive' },
    })
    fireEvent.change(screen.getByLabelText('Organization (required)'), {
      target: { value: 'Example Org' },
    })
    expect(screen.getByRole('option', { name: 'Volunteer' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'volunteer' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save opportunity' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({
      opportunity_type: 'volunteer',
    })
  })

  it('filters the list by Volunteer', async () => {
    const calls = mockApi({
      ...loggedIn,
      ...noSources,
      'GET /api/opportunities': () => listPage([]),
    })
    renderAt('/opportunities')
    const select = await screen.findByLabelText('Type')
    expect(within(select).getByRole('option', { name: 'All types' })).toBeInTheDocument()
    fireEvent.change(select, { target: { value: 'volunteer' } })
    await waitFor(() =>
      expect(calls.some((c) => c.path.includes('opportunity_type=volunteer'))).toBe(true),
    )
  })

  it('labels Volunteer in the list and detail', async () => {
    const volunteer = { opportunity_type: 'volunteer' }
    mockApi({
      ...loggedIn,
      ...noSources,
      'GET /api/opportunities': () => listPage([summary(volunteer)]),
      'GET /api/opportunities/opp-1': () => detail(volunteer),
    })
    const list = renderAt('/opportunities')
    expect(await screen.findByText(/Example Institute · Volunteer/)).toBeInTheDocument()
    list.unmount()

    renderAt('/opportunities/opp-1')
    expect(await screen.findByText('Volunteer')).toBeInTheDocument()
  })
})
