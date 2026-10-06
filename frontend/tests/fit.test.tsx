import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  detail,
  discoveryResponse,
  json,
  listPage,
  loggedIn,
  mockApi,
  renderAt,
  run,
  source,
  summary,
} from './helpers'

// Synthetic Match Profile and fit data only.

const emptyMatch = {
  skills: [],
  courses: [],
  projects: [],
  research: [],
  activities: [],
  experience: [],
  interests: [],
  preferred_locations: [],
  remote_preference: null,
  availability_start: null,
  availability_end: null,
}

const component = (changes: Record<string, unknown> = {}) => ({
  score: 0,
  weight: 10,
  missing: false,
  missing_input: null,
  reason: '',
  matched: [],
  unmatched: [],
  details: null,
  ...changes,
})

const breakdown = {
  scoring_version: 'v1',
  score: 46,
  coverage: 65,
  components: {
    technical: component({
      score: 67,
      weight: 35,
      reason: 'Matched 2 of 3 skills: Python, SQL.',
      matched: ['Python', 'SQL'],
      unmatched: ['Rust'],
    }),
    academic: component({
      weight: 20,
      missing: true,
      missing_input: 'profile',
      reason: 'Add courses to your Match Profile to score this.',
    }),
    projects: component({
      weight: 15,
      missing: true,
      missing_input: 'profile',
      reason: 'Add projects or research to your Match Profile to score this.',
    }),
    interests: component({ score: 100, reason: 'Matched 1 of 1 interests: robotics.' }),
    location_schedule: component({
      missing: true,
      missing_input: 'opportunity',
      reason: 'The posting has no start date, so availability can’t be compared.',
    }),
    quality: component({
      score: 45,
      reason: 'Has an application link, a deadline.',
      matched: ['an application link', 'a deadline'],
      unmatched: ['a start date'],
    }),
  },
}

describe('Match Profile', () => {
  it('edits chips, items, work mode, and availability, then saves once', async () => {
    let resolveSave: (value: Response) => void = () => {}
    const calls = mockApi({
      ...loggedIn,
      'GET /api/profile/match': () => ({ ...emptyMatch, skills: ['Python'] }),
      'PUT /api/profile/match': () =>
        new Promise<Response>((resolve) => {
          resolveSave = resolve
        }),
    })
    renderAt('/profile/match')

    expect(await screen.findByRole('link', { name: 'Match Profile' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    const skills = await screen.findByLabelText('Skills')
    fireEvent.change(skills, { target: { value: 'C++' } })
    fireEvent.keyDown(skills, { key: 'Enter' }) // adds a chip, doesn't submit
    fireEvent.change(skills, { target: { value: 'python' } })
    expect(screen.getByRole('button', { name: 'Add to Skills' })).toBeDisabled() // duplicate
    fireEvent.click(screen.getByRole('button', { name: 'Remove Python' }))

    fireEvent.change(screen.getByLabelText('Preferred locations'), {
      target: { value: 'San Jose, CA' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add to Preferred locations' }))

    fireEvent.click(screen.getByRole('button', { name: 'Add project' }))
    const project = screen.getByRole('group', { name: 'Project 1' })
    fireEvent.change(within(project).getByLabelText('Name'), {
      target: { value: 'Synthetic Rover' },
    })
    fireEvent.change(within(project).getByLabelText('Description (optional)'), {
      target: { value: '  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add research item' })) // left blank

    fireEvent.change(screen.getByLabelText('Work mode preference'), {
      target: { value: 'hybrid_preferred' },
    })
    fireEvent.change(screen.getByLabelText('Available from'), {
      target: { value: '2041-06-15' },
    })
    fireEvent.change(screen.getByLabelText('Available until'), {
      target: { value: '2041-08-31' },
    })

    expect(calls.filter((c) => c.method === 'PUT')).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Save Match Profile' }))

    expect(
      await screen.findByText(/Saving and rescoring opportunities/),
    ).toBeInTheDocument()
    const puts = calls.filter((c) => c.method === 'PUT')
    expect(puts).toHaveLength(1)
    expect(puts[0].headers['X-CSRF-Token']).toBe('synthetic-csrf')
    const sent = {
      ...emptyMatch,
      skills: ['C++'],
      preferred_locations: ['San Jose, CA'],
      projects: [{ name: 'Synthetic Rover', description: null }],
      remote_preference: 'hybrid_preferred',
      availability_start: '2041-06-15',
      availability_end: '2041-08-31',
    }
    expect(puts[0].body).toEqual(sent)

    resolveSave(
      json({
        match_profile: sent,
        evaluated_opportunities: 12,
        unchanged_opportunities: 3,
      }),
    )
    expect(
      await screen.findByText(
        'Match Profile saved. 12 opportunities rescored, 3 unchanged.',
      ),
    ).toBeInTheDocument()
  })

  it('shows field errors and a waking message without losing edits', async () => {
    let attempt = 0
    mockApi({
      ...loggedIn,
      'GET /api/profile/match': () => emptyMatch,
      'PUT /api/profile/match': () =>
        ++attempt === 1
          ? json(
              {
                detail: [
                  {
                    loc: ['body', 'availability_end'],
                    msg: "Value error, availability_end can't be before availability_start",
                  },
                ],
              },
              422,
            )
          : new Response('<html>waking</html>', { status: 502 }),
    })
    renderAt('/profile/match')
    fireEvent.change(await screen.findByLabelText('Interests'), {
      target: { value: 'robotics' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add to Interests' }))

    fireEvent.click(screen.getByRole('button', { name: 'Save Match Profile' }))
    expect(
      await screen.findByText("availability_end can't be before availability_start"),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Save Match Profile' }))
    expect(await screen.findByText(/it may be waking up/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove robotics' })).toBeInTheDocument()
  })

  it('is a separate section from the eligibility profile', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/profile': () => json({ detail: 'No profile yet.' }, 404),
      'GET /api/profile/match': () => emptyMatch,
    })
    renderAt('/profile')
    fireEvent.click(await screen.findByRole('link', { name: 'Match Profile' }))
    expect(
      await screen.findByRole('heading', { name: 'Match Profile' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/never changes eligibility/)).toBeInTheDocument()
  })
})

describe('fit in the opportunity list', () => {
  it('asks for recommended order by default, shows fit next to eligibility, and can sort by newest', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/opportunities': () =>
        listPage([
          summary({ id: 'a', title: 'Scored', fit_score: 82, fit_coverage: 100 }),
          summary({
            id: 'b',
            title: 'Partly scored',
            eligibility_status: 'ineligible',
            fit_score: 40,
            fit_coverage: 45,
          }),
          summary({ id: 'c', title: 'Unscored', eligibility_status: null }),
        ]),
    })
    renderAt('/opportunities')

    const [scored, partly, unscored] = await screen.findAllByRole('listitem')
    expect(within(scored).getByText('Fit 82')).toBeInTheDocument()
    expect(within(scored).getByText('Eligible')).toBeInTheDocument()
    expect(within(scored).queryByText(/of fit measured/)).not.toBeInTheDocument()
    expect(within(partly).getByText('Fit 40')).toBeInTheDocument()
    expect(within(partly).getByText('(45% of fit measured)')).toBeInTheDocument()
    expect(within(partly).getByText('Ineligible')).toBeInTheDocument()
    expect(within(unscored).getByText('Fit not scored yet')).toBeInTheDocument()

    const query = () =>
      new URLSearchParams(
        calls
          .filter((c) => c.path.startsWith('/api/opportunities'))
          .at(-1)!
          .path.split('?')[1],
      )
    expect(query().get('sort')).toBe('recommended')
    expect(screen.getByLabelText('Sort')).toHaveValue('recommended')

    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'newest' } })
    await waitFor(() => expect(query().get('sort')).toBe('newest'))
  })
})

describe('Why this match?', () => {
  it('shows each component, what matched, and what is missing', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({
          latest_evaluation: {
            ...detail().latest_evaluation,
            fit_score: 46,
            scoring_version: 'v1',
            score_breakdown: breakdown,
          },
        }),
    })
    renderAt('/opportunities/opp-1')

    const panel = await screen.findByRole('region', { name: /Why this match/ })
    expect(within(panel).getByText('Fit 46')).toBeInTheDocument()
    expect(
      within(panel).getByText(/Only 65% of the score could be measured/),
    ).toBeInTheDocument()
    const items = within(panel).getAllByRole('listitem')
    expect(items).toHaveLength(6)
    expect(items[0]).toHaveTextContent('Technical skills')
    expect(items[0]).toHaveTextContent('67/100 · weight 35%')
    expect(items[0]).toHaveTextContent('Matched 2 of 3 skills: Python, SQL.')
    expect(within(items[0]).getByText('Rust')).toBeInTheDocument()
    expect(items[1]).toHaveTextContent('Not measured · weight 20%')
    expect(items[1]).toHaveTextContent('Missing from your Match Profile.')
    expect(items[4]).toHaveTextContent("The posting doesn't include this information.")
    expect(items[5]).toHaveTextContent('Posting quality')
    expect(items[5]).toHaveTextContent('Missing: a start date')
    // Eligibility is still shown on its own.
    expect(screen.getByRole('region', { name: 'Eligibility' })).toBeInTheDocument()
  })

  it('explains how to get a score when there is none', async () => {
    mockApi({ ...loggedIn, 'GET /api/opportunities/opp-1': () => detail() })
    renderAt('/opportunities/opp-1')
    const panel = await screen.findByRole('region', { name: /Why this match/ })
    expect(panel).toHaveTextContent('No fit score yet.')
    expect(within(panel).getByRole('link', { name: 'Match Profile' })).toHaveAttribute(
      'href',
      '/profile/match',
    )
  })
})

describe('source scope', () => {
  const board = source({
    id: 'src-gh',
    kind: 'greenhouse',
    key: 'greenhouse:examplerobotics',
    identifier: 'examplerobotics',
    display_name: 'Example Robotics',
    scope: 'internships_only',
    builtin: false,
    latest_run: run({ source_id: 'src-gh', fetched_count: 5, filtered_count: 3 }),
  })

  it('adds a board with all postings when chosen', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [source()],
      'POST /api/sources': () => json({ ...board, scope: 'all', latest_run: null }, 201),
    })
    renderAt('/sources')
    expect(await screen.findByLabelText('Import')).toHaveValue('internships_only')
    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Example Robotics' },
    })
    fireEvent.change(screen.getByLabelText('Job board link or name'), {
      target: { value: 'examplerobotics' },
    })
    fireEvent.change(screen.getByLabelText('Import'), { target: { value: 'all' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add source' }))
    await screen.findByText(/Added Example Robotics/)
    expect(calls.filter((c) => c.method === 'POST').at(-1)!.body).toMatchObject({
      scope: 'all',
    })
  })

  it('shows filtered counts and switches a board scope', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [source(), board],
      'PUT /api/sources/src-gh': () => ({ ...board, scope: 'all' }),
    })
    renderAt('/sources')

    // Wait for both cards: findAllBy resolves on the first listitem, before the list is complete.
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2))
    const card = screen.getAllByRole('listitem')[1]
    expect(card).toHaveTextContent('Filtered: 3')
    const select = within(card).getByLabelText('Import')
    expect(select).toHaveValue('internships_only')
    // The built-in feed has no scope control.
    expect(screen.getAllByLabelText('Import')).toHaveLength(2) // the card + the add form

    fireEvent.change(select, { target: { value: 'all' } })
    expect(
      await screen.findByText(
        'Example Robotics: All postings. The next sync applies it.',
      ),
    ).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'PUT').at(-1)!.body).toEqual({
      display_name: 'Example Robotics',
      enabled: true,
      scope: 'all',
    })
  })
})
