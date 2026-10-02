import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  candidate,
  detail,
  json,
  loggedIn,
  mockApi,
  renderAt,
  requirementReview,
} from './helpers'

// Synthetic opportunities and candidates only.

const ageCandidate = candidate() // minimum_age, years: 16, pending
const educationCandidate = candidate({
  id: 'cand-2',
  requirement_type: 'education',
  value: { levels: ['undergraduate'], accepts_incoming: false },
  source_text: 'Currently enrolled undergraduate students only.',
})
const citizenshipCandidate = candidate({
  id: 'cand-3',
  requirement_type: 'citizenship',
  value: { countries: ['US'] },
  source_text: 'U.S. citizenship is preferred.',
})

async function openPanel() {
  renderAt('/opportunities/opp-1')
  // The loading state renders the same named region, so wait for content that only exists once
  // the review has loaded before grabbing a (now stable) reference to it.
  await screen.findByText('Pending suggestions')
  return screen.getByRole('region', { name: 'Requirement Review' })
}

describe('requirement review panel', () => {
  it('shows pending, accepted, and rejected suggestions with human-readable values', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(),
      'GET /api/opportunities/opp-1/requirement-review': () =>
        requirementReview({
          candidates: [
            ageCandidate,
            candidate({
              id: 'cand-4',
              review_state: 'accepted',
              accepted_requirement_id: 'req-9',
            }),
            candidate({ id: 'cand-5', review_state: 'rejected' }),
          ],
        }),
    })
    const panel = await openPanel()

    expect(within(panel).getByText('Pending suggestions')).toBeInTheDocument()
    expect(within(panel).getByText('Accepted')).toBeInTheDocument()
    expect(within(panel).getByText('Rejected')).toBeInTheDocument()
    expect(within(panel).getAllByText('at least 16 years old').length).toBe(3)
    expect(within(panel).queryByText(/"years":\s*16/)).not.toBeInTheDocument()
    expect(
      within(panel).getByRole('button', { name: 'Accept minimum age 16' }),
    ).toBeInTheDocument()
  })

  it('shows an accepted suggestion with the value the owner accepted, not the original', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(),
      'GET /api/opportunities/opp-1/requirement-review': () =>
        requirementReview({
          candidates: [
            candidate({
              review_state: 'accepted',
              accepted_requirement_id: 'req-edited',
            }),
          ],
          requirements: [
            {
              id: 'req-edited',
              requirement_type: 'minimum_age',
              value: { years: 19 },
              applies_at: 'program_start',
              reference_date: null,
              source_text: 'Applicants must be at least 16 years old.',
              extraction_method: 'deterministic_parser',
              extractor_name: 'requirements-rules',
              extractor_version: '1',
            },
          ],
        }),
    })
    const panel = await openPanel()

    const accepted = within(panel).getByRole('region', { name: 'Accepted' })
    expect(within(accepted).getByText('at least 19 years old')).toBeInTheDocument()
    expect(within(accepted).queryByText('at least 16 years old')).not.toBeInTheDocument()
  })

  it('renders the source excerpt as text, never HTML', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(),
      'GET /api/opportunities/opp-1/requirement-review': () =>
        requirementReview({
          candidates: [candidate({ source_text: '<img src=x onerror=alert(1)>' })],
        }),
    })
    const panel = await openPanel()

    expect(within(panel).getByText(/img src=x onerror=alert\(1\)/)).toBeInTheDocument()
    expect(panel.querySelector('img')).toBeNull()
  })

  it('shows the stale warning', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(),
      'GET /api/opportunities/opp-1/requirement-review': () =>
        requirementReview({ requirements_stale_since: '2041-01-01T00:00:00Z' }),
    })
    const panel = await openPanel()

    expect(
      within(panel).getByText(
        'Posting changed since requirement review. Review requirements again.',
      ),
    ).toBeInTheDocument()
  })

  it('sends one batch matching accept, edited accept, reject, and the chosen assessment status', async () => {
    let getCount = 0
    const calls = mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => {
        getCount += 1
        return getCount === 1
          ? detail()
          : detail({
              latest_evaluation: {
                ...detail().latest_evaluation,
                eligibility_status: 'eligible',
              },
            })
      },
      'GET /api/opportunities/opp-1/requirement-review': () =>
        requirementReview({
          candidates: [ageCandidate, educationCandidate, citizenshipCandidate],
        }),
      'POST /api/opportunities/opp-1/requirement-review': () => ({
        review: requirementReview({
          requirements_assessment_status: 'complete',
          candidates: [],
        }),
        evaluated: true,
      }),
    })
    const panel = await openPanel()

    fireEvent.click(within(panel).getByRole('button', { name: 'Accept minimum age 16' }))
    fireEvent.click(
      within(panel).getByRole('button', { name: 'Edit education (undergraduate)' }),
    )
    fireEvent.click(within(panel).getByLabelText(/Incoming students accepted/))
    fireEvent.click(
      within(panel).getByRole('button', { name: 'Reject citizenship (US)' }),
    )
    fireEvent.click(
      within(panel).getByRole('radio', { name: /All hard requirements reviewed/ }),
    )
    fireEvent.click(within(panel).getByRole('button', { name: /Apply changes/ }))

    const posts = calls.filter((c) => c.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(posts[0].body).toEqual({
      accept: [
        { id: 'cand-1' },
        {
          id: 'cand-2',
          value: { levels: ['undergraduate'], accepts_incoming: true },
          applies_at: 'program_start',
          reference_date: null,
        },
      ],
      reject: ['cand-3'],
      assessment_status: 'complete',
    })
    // The opportunity reloads afterward, so the Eligibility panel reflects the new review.
    await waitFor(() => expect(getCount).toBe(2))
  })

  it('marks requirements complete on its own, with nothing staged', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(),
      'GET /api/opportunities/opp-1/requirement-review': () => requirementReview(),
      'POST /api/opportunities/opp-1/requirement-review': () => ({
        review: requirementReview({ requirements_assessment_status: 'complete' }),
        evaluated: true,
      }),
    })
    const panel = await openPanel()

    fireEvent.click(
      within(panel).getByRole('radio', { name: /All hard requirements reviewed/ }),
    )
    fireEvent.click(within(panel).getByRole('button', { name: /Apply changes/ }))

    const posts = calls.filter((c) => c.method === 'POST')
    expect(posts).toHaveLength(1)
    expect(posts[0].body).toEqual({
      accept: [],
      reject: [],
      assessment_status: 'complete',
    })
  })

  it('shows a validation error from the backend without applying it silently', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(),
      'GET /api/opportunities/opp-1/requirement-review': () => requirementReview(),
      'POST /api/opportunities/opp-1/requirement-review': () =>
        json({ detail: 'That candidate no longer exists.' }, 404),
    })
    const panel = await openPanel()

    fireEvent.click(within(panel).getByRole('button', { name: 'Accept minimum age 16' }))
    fireEvent.click(within(panel).getByRole('button', { name: /Apply changes/ }))

    expect(await within(panel).findByRole('alert')).toHaveTextContent(
      'That candidate no longer exists.',
    )
  })

  it('refreshes suggestions on request', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(),
      'GET /api/opportunities/opp-1/requirement-review': () => requirementReview(),
      'POST /api/opportunities/opp-1/requirement-review/refresh': () =>
        requirementReview({
          candidates: [candidate({ id: 'cand-new', value: { years: 18 } })],
        }),
    })
    const panel = await openPanel()

    fireEvent.click(within(panel).getByRole('button', { name: 'Refresh suggestions' }))

    expect(await within(panel).findByText('at least 18 years old')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.path.endsWith('/refresh'))).toBe(
      true,
    )
  })
})
