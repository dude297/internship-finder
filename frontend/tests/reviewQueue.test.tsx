import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  candidate,
  json,
  loggedIn,
  mockApi,
  renderAt,
  requirementReview,
} from './helpers'
import { moveCursor, pruneSelection, shortcutFor } from '../src/lib/reviewQueue'

// Synthetic data only.

const queueItem = (id: string, over: Record<string, unknown> = {}) => ({
  candidate: candidate({ id, ...(over.candidate as object) }),
  opportunity: {
    id: `opp-${id}`,
    title: `Example Program ${id}`,
    organization: 'Example Org',
    application_url: null,
    first_seen_at: '2040-10-01T12:00:00Z',
    requirements_assessment_status: 'unassessed',
    requirements_stale_since: null,
    freshness: 'manual',
    freshness_checked_at: null,
    source_names: ['manual'],
    source_kinds: [],
  },
  existing_requirements: [],
  duplicate_of: null,
  ...over,
  ...(over.candidate
    ? { candidate: candidate({ id, ...(over.candidate as object) }) }
    : {}),
})

const queue = (items: unknown[], over: Record<string, unknown> = {}) => ({
  items,
  total: items.length,
  limit: 50,
  offset: 0,
  summary: {
    pending_total: items.length,
    by_type: [{ requirement_type: 'minimum_age', count: items.length }],
    accepted_today: 2,
    rejected_today: 1,
    today: '2040-10-05',
    extractor_versions: ['1'],
  },
  ...over,
})

const reviewResult = { review: requirementReview(), evaluated: false }

describe('shortcut rules', () => {
  const base = {
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    repeat: false,
    target: null,
  }

  it('maps letters, ignoring case', () => {
    expect(shortcutFor({ ...base, key: 'a' })).toBe('accept')
    expect(shortcutFor({ ...base, key: 'E' })).toBe('edit')
    expect(shortcutFor({ ...base, key: 'r' })).toBe('reject')
    expect(shortcutFor({ ...base, key: 's' })).toBe('skip')
    expect(shortcutFor({ ...base, key: 'j' })).toBe('next')
    expect(shortcutFor({ ...base, key: 'k' })).toBe('previous')
    expect(shortcutFor({ ...base, key: 'x' })).toBeNull()
  })

  it('never fires with modifiers, key repeat, or while typing', () => {
    expect(shortcutFor({ ...base, key: 'a', ctrlKey: true })).toBeNull()
    expect(shortcutFor({ ...base, key: 'a', metaKey: true })).toBeNull()
    expect(shortcutFor({ ...base, key: 'a', repeat: true })).toBeNull()
    for (const tag of ['input', 'textarea', 'select']) {
      expect(
        shortcutFor({ ...base, key: 'a', target: document.createElement(tag) }),
      ).toBeNull()
    }
    expect(
      shortcutFor({ ...base, key: 'a', target: document.createElement('div') }),
    ).toBe('accept')
  })

  it('clamps the cursor and prunes selections', () => {
    expect(moveCursor(0, -1, 3)).toBe(0)
    expect(moveCursor(2, 1, 3)).toBe(2)
    expect(moveCursor(1, 1, 3)).toBe(2)
    expect(moveCursor(5, 0, 0)).toBe(0)
    expect([...pruneSelection(new Set(['a', 'b']), ['b', 'c'])]).toEqual(['b'])
  })
})

describe('requirement review queue page', () => {
  it('shows progress, the focused card with evidence, and the shortcut hint', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/requirement-review/queue': () =>
        queue([
          queueItem('c1', {
            existing_requirements: [
              {
                id: 'req-1',
                requirement_type: 'education',
                value: { levels: ['undergraduate'], accepts_incoming: false },
                applies_at: 'program_start',
                reference_date: null,
                source_text: null,
                extraction_method: 'manual',
                extractor_name: null,
                extractor_version: null,
              },
            ],
          }),
          queueItem('c2'),
        ]),
    })
    renderAt('/requirements')

    const card = await screen.findByRole('region', { name: 'Current suggestion' })
    expect(within(card).getByText('Example Program c1')).toBeInTheDocument()
    expect(
      within(card).getByText('Applicants must be at least 16 years old.').tagName,
    ).toBe('MARK')
    expect(within(card).getByText(/undergraduate/)).toBeInTheDocument()
    const progress = screen.getByRole('region', { name: 'Progress' })
    expect(within(progress).getByText(/2 accepted, 1/)).toBeInTheDocument()
    expect(within(progress).getByText('Minimum age: 2')).toBeInTheDocument()
    expect(screen.getByLabelText('Keyboard shortcuts')).toHaveTextContent('reject')
  })

  it('warns when the suggestion duplicates an existing requirement', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/requirement-review/queue': () =>
        queue([queueItem('c1', { duplicate_of: 'req-1' })]),
    })
    renderAt('/requirements')

    expect(await screen.findByText(/no duplicate is created/)).toBeInTheDocument()
  })

  it('accepts through the existing review endpoint, then reloads the queue', async () => {
    let served = 0
    const calls = mockApi({
      ...loggedIn,
      'GET /api/requirement-review/queue': () =>
        queue(served++ === 0 ? [queueItem('c1'), queueItem('c2')] : [queueItem('c2')]),
      'POST /api/opportunities/opp-c1/requirement-review': () => reviewResult,
    })
    renderAt('/requirements')

    fireEvent.click(await screen.findByRole('button', { name: 'Accept' }))

    expect(await screen.findByText('Accepted.')).toBeInTheDocument()
    await screen.findByText('Example Program c2', { selector: 'a' })
    const post = calls.find((c) => c.method === 'POST')
    expect(post?.path).toBe('/api/opportunities/opp-c1/requirement-review')
    expect(post?.body).toEqual({ accept: [{ id: 'c1' }], reject: [] })
    expect(post?.headers['X-CSRF-Token']).toBe('synthetic-csrf')
  })

  it('rejects one suggestion with the keyboard but not while typing in a field', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/requirement-review/queue': () => queue([queueItem('c1')]),
      'POST /api/opportunities/opp-c1/requirement-review': () => reviewResult,
    })
    renderAt('/requirements')
    await screen.findByRole('region', { name: 'Current suggestion' })

    const org = screen.getByLabelText('Organization contains')
    fireEvent.keyDown(org, { key: 'r' })
    expect(calls.some((c) => c.method === 'POST')).toBe(false)

    fireEvent.keyDown(window, { key: 'r' })
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      accept: [],
      reject: ['c1'],
    })
  })

  it('edits then accepts with the edited value', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/requirement-review/queue': () => queue([queueItem('c1')]),
      'POST /api/opportunities/opp-c1/requirement-review': () => reviewResult,
    })
    renderAt('/requirements')

    fireEvent.click(await screen.findByRole('button', { name: 'Edit + Accept' }))
    fireEvent.change(screen.getByLabelText('Minimum age (years)'), {
      target: { value: '18' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save edit and accept' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(calls.find((c) => c.method === 'POST')?.body).toMatchObject({
      accept: [{ id: 'c1', value: { years: 18 } }],
    })
  })

  it('skip and next/previous move without calling the server', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/requirement-review/queue': () =>
        queue([queueItem('c1'), queueItem('c2')]),
    })
    renderAt('/requirements')
    const card = () => screen.getByRole('region', { name: 'Current suggestion' })
    await screen.findByRole('region', { name: 'Current suggestion' })

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    expect(within(card()).getByText('Example Program c2')).toBeInTheDocument()
    expect(within(card()).getByText(/Suggestion 2 of 2/)).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'k' })
    expect(within(card()).getByText('Example Program c1')).toBeInTheDocument()
    expect(within(card()).getByText(/skipped/)).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('batch-rejects the selection only after confirmation', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/requirement-review/queue': () =>
        queue([queueItem('c1'), queueItem('c2')]),
      'POST /api/requirement-review/reject-batch': () =>
        json({ rejected: 2, opportunities: 2, evaluated: 0 }),
    })
    renderAt('/requirements')
    await screen.findByRole('region', { name: 'Loaded suggestions' })

    fireEvent.click(screen.getByRole('button', { name: 'Select all loaded' }))
    fireEvent.click(screen.getByRole('button', { name: 'Reject selected (2)' }))
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm reject' }))

    expect(await screen.findByText('Rejected 2 suggestions.')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      candidate_ids: ['c1', 'c2'],
    })
  })

  it('has no accept-all control and sends filters to the API', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/requirement-review/queue': () => queue([queueItem('c1')]),
    })
    renderAt('/requirements')
    await screen.findByRole('region', { name: 'Current suggestion' })
    expect(
      screen.queryByRole('button', { name: /accept (all|selected|category)/i }),
    ).toBeNull()

    fireEvent.change(screen.getByLabelText('Category'), {
      target: { value: 'education' },
    })
    fireEvent.change(screen.getByLabelText('Organization contains'), {
      target: { value: 'Example' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() =>
      expect(calls.some((c) => c.path.includes('requirement_type=education'))).toBe(true),
    )
    expect(calls.at(-1)?.path).toContain('organization=Example')
  })

  it('shows an error with a retry, and an empty state', async () => {
    let fail = true
    mockApi({
      ...loggedIn,
      'GET /api/requirement-review/queue': () =>
        fail ? json({ detail: 'Boom' }, 500) : queue([]),
    })
    renderAt('/requirements')

    expect(await screen.findByRole('alert')).toHaveTextContent('Boom')
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/Nothing to review/)).toBeInTheDocument()
  })
})
