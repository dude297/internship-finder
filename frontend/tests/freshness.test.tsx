import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { FreshnessState } from '../src/api/schemas'
import {
  FreshnessBadge,
  FreshnessSection,
  NewBadge,
} from '../src/components/FreshnessBadge'
import { isNewlyFound, relativeAge } from '../src/lib/freshness'
import {
  coverageMetrics,
  detail,
  discoveryResponse,
  feedRecord,
  json,
  listPage,
  loggedIn,
  mockApi,
  renderAt,
  source,
  summary,
} from './helpers'

// Synthetic data only.

const NOW = Date.parse('2040-10-05T12:00:00Z')
const ago = (ms: number) => new Date(NOW - ms).toISOString()
const H = 3_600_000
const D = 24 * H

const base = {
  freshness_checked_at: ago(3 * H),
  program_last_verified: null,
  verify_by: null,
}

function badgeText(freshness: FreshnessState, extra = {}, compact = false) {
  const { container } = render(
    <FreshnessBadge o={{ ...base, freshness, ...extra }} compact={compact} now={NOW} />,
  )
  return container
}

describe('relative age', () => {
  it('formats minutes, hours, days', () => {
    expect(relativeAge(ago(10_000), NOW)).toBe('just now')
    expect(relativeAge(ago(5 * 60_000), NOW)).toBe('5m ago')
    expect(relativeAge(ago(3 * H), NOW)).toBe('3h ago')
    expect(relativeAge(ago(2 * D + H), NOW)).toBe('2d ago')
  })
})

describe('New badge boundary', () => {
  it('is new at 6.9 days and not at 7.1 days', () => {
    expect(isNewlyFound(ago(6.9 * D), NOW)).toBe(true)
    expect(isNewlyFound(ago(7.1 * D), NOW)).toBe(false)
    const { container } = render(
      <NewBadge firstSeenAt={ago(7.1 * D)} postedAt={null} now={NOW} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('explains first-found versus company posted date', () => {
    render(<NewBadge firstSeenAt={ago(D)} postedAt="2040-09-01T00:00:00Z" now={NOW} />)
    const badge = screen.getByText('New')
    expect(badge).toHaveAttribute(
      'title',
      expect.stringMatching(/First found by Internship Finder on/),
    )
    expect(badge).toHaveAttribute('title', expect.stringMatching(/Posted by the company/))
  })
})

describe('freshness badge', () => {
  it('direct_verified shows ATS wording with relative age and a tooltip', () => {
    badgeText('direct_verified')
    const badge = screen.getByText('ATS verified · 3h ago')
    expect(badge).toHaveAttribute(
      'title',
      expect.stringContaining("company's own job board"),
    )
    expect(badge).toHaveAttribute('title', expect.stringContaining('3h ago'))
  })

  it('program_listed shows dates and omits missing parts', () => {
    badgeText('program_listed', {
      program_last_verified: '2040-10-04',
      verify_by: '2040-10-09',
    })
    expect(screen.getByText(/Program checked .* · re-check /)).toBeInTheDocument()
  })

  it('program_listed with only verify_by omits the checked part', () => {
    badgeText('program_listed', { verify_by: '2040-10-09' })
    expect(screen.getByText(/^re-check /)).toBeInTheDocument()
  })

  it('program_recheck, feed_current, source_warning wording', () => {
    badgeText('program_recheck')
    expect(screen.getByText('Program info needs re-check')).toBeInTheDocument()
    badgeText('feed_current')
    expect(screen.getByText('Feed current · 3h ago')).toBeInTheDocument()
    badgeText('source_warning')
    const warn = screen.getByText('Verification incomplete')
    expect(warn).toHaveAttribute(
      'title',
      expect.stringContaining('may still appear open'),
    )
  })

  it('manual shows only in detail; closed never; list stays quiet', () => {
    expect(badgeText('manual', {}, true)).toBeEmptyDOMElement()
    expect(badgeText('closed')).toBeEmptyDOMElement()
    badgeText('manual')
    expect(screen.getByText('Added manually')).toBeInTheDocument()
  })

  it('never promises an open posting', () => {
    const states: FreshnessState[] = [
      'direct_verified',
      'program_listed',
      'program_recheck',
      'feed_current',
      'source_warning',
      'manual',
    ]
    for (const s of states) {
      const c = badgeText(s, {
        program_last_verified: '2040-10-04',
        verify_by: '2040-10-09',
      })
      const text = `${c.textContent} ${c.querySelector('[title]')?.getAttribute('title') ?? ''}`
      expect(text).not.toMatch(/guaranteed|definitely/i)
    }
  })
})

describe('freshness section', () => {
  it('shows per-source health and last successful sync', () => {
    const d = detail({
      freshness: 'direct_verified',
      freshness_checked_at: ago(3 * H),
      sources: [
        feedRecord({
          source_name: 'Example Board',
          source_health: 'healthy',
          source_last_success_at: '2040-10-05T09:00:00Z',
        }),
        feedRecord({
          source_name: 'Old Board',
          source_health: 'stale',
          source_last_success_at: null,
        }),
      ],
    })
    render(<FreshnessSection opportunity={d as never} now={NOW} />)
    expect(screen.getByRole('heading', { name: 'Freshness' })).toBeInTheDocument()
    expect(
      screen.getByText(/Verified on the company's own job board/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Example Board/).parentElement).toHaveTextContent('Healthy')
    expect(screen.getByText(/Old Board/).parentElement).toHaveTextContent(
      'Stale · Last successful sync: never',
    )
  })
})

describe('list and detail pages', () => {
  it('list card shows New and one freshness badge', async () => {
    const firstSeen = new Date(Date.now() - D).toISOString()
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/opportunities': () =>
        listPage([
          summary({
            first_seen_at: firstSeen,
            freshness: 'feed_current',
            freshness_checked_at: new Date().toISOString(),
          }),
        ]),
    })
    renderAt('/opportunities')
    expect(await screen.findByText('New')).toBeInTheDocument()
    expect(screen.getByText(/^Feed current/)).toBeInTheDocument()
  })

  it('detail header and Freshness section render', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({
          freshness: 'source_warning',
          sources: [
            feedRecord({
              source_health: 'warning',
              source_last_success_at: '2040-10-01T12:00:00Z',
            }),
          ],
        }),
    })
    renderAt('/opportunities/opp-1')
    expect(await screen.findByText('Verification incomplete')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Freshness' })).toBeInTheDocument()
  })
})

describe('filters', () => {
  it('sends freshness, discovered_within and sort=discovered', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/opportunities': () => listPage([summary()]),
    })
    renderAt('/opportunities')
    await screen.findByText('Example Summer Research Program')

    fireEvent.change(screen.getByLabelText('Freshness'), {
      target: { value: 'direct_verified' },
    })
    fireEvent.change(screen.getByLabelText('Discovered'), { target: { value: '7' } })
    fireEvent.change(screen.getByLabelText('Sort'), { target: { value: 'discovered' } })

    await waitFor(() => {
      const last = calls.filter((c) => c.path.startsWith('/api/opportunities?')).at(-1)!
      const params = new URLSearchParams(last.path.split('?')[1])
      expect(params.get('freshness')).toBe('direct_verified')
      expect(params.get('discovered_within')).toBe('7')
      expect(params.get('sort')).toBe('discovered')
    })
  })

  it('reads the filters from the URL and offers the wording options', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/opportunities': () => listPage([summary()]),
    })
    renderAt('/opportunities?freshness=needs_review&discovered_within=1')
    await screen.findByText('Example Summer Research Program')
    const params = new URLSearchParams(
      calls.find((c) => c.path.startsWith('/api/opportunities?'))!.path.split('?')[1],
    )
    expect(params.get('freshness')).toBe('needs_review')
    expect(params.get('discovered_within')).toBe('1')
    expect(
      screen.getByRole('option', { name: 'Needs freshness review' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'New today' })).toBeInTheDocument()
    expect(
      screen.getByRole('option', { name: 'Recently discovered' }),
    ).toBeInTheDocument()
  })
})

describe('independent coverage', () => {
  it('renders the independent coverage line and breakdown', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () =>
        discoveryResponse({
          coverage: coverageMetrics({
            active_opportunities: 1626,
            independent: 629,
            independent_percent: 38.7,
            direct_fresh: 321,
          }),
        }),
    })
    renderAt('/sources')
    expect(
      await screen.findByText('629 of 1,626 survive without the community feed'),
    ).toBeInTheDocument()
    expect(screen.getByText('Independent discovery').closest('div')).toHaveTextContent(
      '38.7%',
    )
    expect(screen.getByText('Direct ATS, verified fresh')).toBeInTheDocument()
    expect(screen.getByText('321')).toBeInTheDocument()
  })
})

const entry = (changes: Record<string, unknown> = {}) => ({
  key: 'greenhouse:examplelabs',
  organization: 'Example Labs',
  kind: 'greenhouse',
  identifier: 'examplelabs',
  region: null,
  careers_url: 'https://careers.example.com/labs',
  evidence: 'https://example.com/api (documented public API, HTTP 200)',
  verified_at: '2040-10-05',
  tags: ['ai'],
  already_configured: false,
  ...changes,
})

describe('verified direct sources', () => {
  it('lists entries, disables configured, filters by tag, links are safe', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources/catalog': () => ({
        entries: [
          entry(),
          entry({
            key: 'lever:examplebio',
            kind: 'lever',
            identifier: 'examplebio',
            organization: 'Example Bio',
            tags: ['biotech'],
            already_configured: true,
          }),
        ],
      }),
    })
    renderAt('/sources')
    expect(
      await screen.findByRole('heading', { name: 'Verified Direct Sources' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Select lever:examplebio')).toBeDisabled()
    const link = screen.getAllByRole('link', { name: 'Careers page' })[0]
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getAllByText(/documented public API/)[0].closest('a')).toBeNull()

    fireEvent.change(screen.getByLabelText('Filter by tag'), { target: { value: 'ai' } })
    expect(screen.queryByText('Example Bio')).not.toBeInTheDocument()
    expect(screen.getByText('Example Labs')).toBeInTheDocument()
  })

  it('adds selected entries with identity only, then reloads sources and catalog', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources/catalog': () => ({ entries: [entry()] }),
      'POST /api/sources/catalog/add': () => ({
        created: [
          source({ id: 'src-gh', kind: 'greenhouse', display_name: 'Example Labs' }),
        ],
        skipped: [],
      }),
    })
    renderAt('/sources')
    fireEvent.click(await screen.findByLabelText('Select greenhouse:examplelabs'))
    fireEvent.click(screen.getByRole('button', { name: 'Add selected (1)' }))

    expect(await screen.findByText(/Added 1, skipped 0/)).toBeInTheDocument()
    const add = calls.find((c) => c.path === '/api/sources/catalog/add')!
    expect(add.body).toEqual({
      sources: [{ kind: 'greenhouse', identifier: 'examplelabs', region: null }],
    })
    expect(add.headers['X-CSRF-Token']).toBe('synthetic-csrf')
    expect(calls.filter((c) => c.path === '/api/sources/catalog')).toHaveLength(2)
    expect(calls.filter((c) => c.path === '/api/sources')).toHaveLength(2)
  })

  it('caps the selection at 25 and shows API errors', async () => {
    const many = Array.from({ length: 26 }, (_, i) =>
      entry({ key: `greenhouse:b${i}`, identifier: `b${i}`, organization: `Org ${i}` }),
    )
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources/catalog': () => ({ entries: many }),
      'POST /api/sources/catalog/add': () =>
        json({ detail: 'One or more sources is not in the catalog.' }, 422),
    })
    renderAt('/sources')
    for (let i = 0; i < 26; i++)
      fireEvent.click(await screen.findByLabelText(`Select greenhouse:b${i}`))
    expect(screen.getByRole('button', { name: 'Add selected (26)' })).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Select greenhouse:b25'))
    fireEvent.click(screen.getByRole('button', { name: 'Add selected (25)' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('not in the catalog')
  })
})
