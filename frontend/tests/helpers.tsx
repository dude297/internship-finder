import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { vi } from 'vitest'
import App from '../src/App'

// Synthetic fixtures only.

export interface Call {
  method: string
  path: string
  body: unknown
  headers: Record<string, string>
}

type Handler = (call: Call) => Response | unknown

export const json = (body: unknown, status = 200) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

/**
 * Stub fetch with handlers keyed by "METHOD /api/path" (an exact key with the query string wins;
 * otherwise the path without it matches). A handler returns a Response, a JSON body, or a
 * Promise (returned as is). Unhandled requests fail the test loudly. Returns the recorded calls.
 */
export function mockApi(handlers: Record<string, Handler>): Call[] {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET'
      const call: Call = {
        method,
        path: input,
        body: typeof init.body === 'string' ? JSON.parse(init.body) : init.body,
        headers: (init.headers ?? {}) as Record<string, string>,
      }
      calls.push(call)
      const handler =
        handlers[`${method} ${input}`] ?? handlers[`${method} ${input.split('?')[0]}`]
      if (!handler)
        return Promise.reject(new Error(`Unhandled request: ${method} ${input}`))
      const result = handler(call)
      if (result instanceof Promise) return result // e.g. a request that never finishes
      return Promise.resolve(result instanceof Response ? result : json(result))
    }),
  )
  return calls
}

export const loggedIn = {
  'GET /api/auth/session': () => ({
    authenticated: true,
    username: 'synthetic-owner',
    csrf_token: 'synthetic-csrf',
  }),
}

export const loggedOut = {
  'GET /api/auth/session': () => ({
    authenticated: false,
    username: null,
    csrf_token: null,
  }),
}

export function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

export const summary = (changes: Record<string, unknown> = {}) => ({
  id: 'opp-1',
  title: 'Example Summer Research Program',
  organization: 'Example Institute',
  opportunity_type: 'research',
  location: 'Example City',
  remote_mode: 'onsite',
  application_deadline: '2041-02-01',
  start_date: '2041-06-20',
  posted_at: null,
  first_seen_at: '2040-10-01T12:00:00Z',
  requirements_assessment_status: 'complete',
  eligibility_status: 'eligible',
  evaluated_at: '2040-10-01T12:00:00Z',
  fit_score: null,
  scoring_version: null,
  fit_coverage: null,
  fit_components: null,
  application_status: null,
  origin: 'manual',
  availability: 'manual',
  source_names: ['Manual entry'],
  ...changes,
})

export const listPage = (items: unknown[], changes: Record<string, unknown> = {}) => ({
  items,
  total: items.length,
  limit: 50,
  offset: 0,
  ...changes,
})

export const manualRecord = {
  source_name: 'Manual entry',
  source_type: 'manual',
  automated: false,
  is_active: true,
  closed_at: null,
  first_seen_at: '2040-10-01T12:00:00Z',
  last_seen_at: '2040-10-01T12:00:00Z',
  source_url: null,
  source_published_at: null,
  source_updated_at: null,
}

export const feedRecord = (changes: Record<string, unknown> = {}) => ({
  ...manualRecord,
  source_name: 'Tech Internship Discovery Feed',
  source_type: 'public_feed',
  automated: true,
  source_url: 'https://careers.example.com/jobs/synthetic-1',
  ...changes,
})

export const run = (changes: Record<string, unknown> = {}) => ({
  id: 'run-1',
  source_id: 'src-feed',
  status: 'success',
  started_at: '2040-10-01T12:00:00Z',
  finished_at: '2040-10-01T12:00:04Z',
  source_generated_at: '2040-10-01T11:50:00Z',
  fetched_count: 3,
  filtered_count: 0,
  normalized_count: 3,
  created_count: 2,
  updated_count: 0,
  deduplicated_count: 1,
  unchanged_count: 0,
  closed_count: 0,
  reactivated_count: 0,
  invalid_count: 0,
  error_count: 0,
  error_summary: null,
  errors: [],
  ...changes,
})

export const source = (changes: Record<string, unknown> = {}) => ({
  id: 'src-feed',
  kind: 'community_feed',
  key: 'community_feed:zshah-tech-internships',
  identifier: 'zshah-tech-internships',
  region: null,
  display_name: 'Tech Internship Discovery Feed',
  enabled: true,
  scope: 'all',
  builtin: true,
  last_attempted_at: null,
  last_success_at: null,
  latest_run: null,
  ...changes,
})

export const importedFact = (changes: Record<string, unknown> = {}) => ({
  id: 'fact-1',
  category: 'skill',
  name: 'Python',
  description: null,
  review_state: 'pending',
  ...changes,
})

export const profileSource = (changes: Record<string, unknown> = {}) => ({
  id: 'psrc-1',
  kind: 'resume',
  original_filename: 'resume.pdf',
  content_type: 'application/pdf',
  byte_size: 12_345,
  parser_name: 'synthetic-parser',
  parser_version: '1.0.0',
  ingested_at: '2040-10-01T12:00:00Z',
  pending_count: 1,
  accepted_count: 0,
  rejected_count: 0,
  ...changes,
})

export const profileSourceDetail = (changes: Record<string, unknown> = {}) => ({
  ...profileSource(),
  facts: [importedFact()],
  ...changes,
})

const projectedEducation = {
  rule_id: 'ELIG-EDU-001',
  requirement_id: 'req-2',
  status: 'eligible',
  reason:
    'Requires undergraduate (incoming accepted) status on 2041-06-20; projected ...',
  reference_date: '2041-06-20',
  depends_on_projected_status: true,
  details: {
    phase: 'incoming',
    level: 'undergraduate',
    explanation:
      'Projected incoming undergraduate on 2041-06-20: expected to graduate high_school on 2041-06-10 and enroll on 2041-08-25.',
  },
}

export const detail = (changes: Record<string, unknown> = {}) => ({
  ...summary(),
  description: 'Synthetic description.',
  application_url: 'https://example.org/apply',
  end_date: '2041-08-01',
  created_at: '2040-10-01T12:00:00Z',
  updated_at: '2040-10-01T12:00:00Z',
  last_seen_at: '2040-10-01T12:00:00Z',
  manually_curated_at: '2040-10-01T12:00:00Z',
  sources: [manualRecord],
  requirements: [
    {
      id: 'req-1',
      requirement_type: 'citizenship',
      value: { countries: ['US'] },
      applies_at: 'program_start',
      reference_date: null,
      source_text: null,
      extraction_method: 'manual',
    },
    {
      id: 'req-2',
      requirement_type: 'education',
      value: { levels: ['undergraduate'], accepts_incoming: true },
      applies_at: 'program_start',
      reference_date: null,
      source_text: null,
      extraction_method: 'manual',
    },
  ],
  application: null,
  profile_exists: true,
  latest_evaluation: {
    id: 'eval-1',
    eligibility_status: 'needs_verification',
    eligibility_rules_version: 'v1',
    depends_on_projected_status: false,
    evaluated_at: '2040-10-01T12:00:00Z',
    fit_score: null,
    scoring_version: null,
    score_breakdown: null,
    rule_results: [
      {
        rule_id: 'ELIG-REQ-000',
        requirement_id: null,
        status: 'eligible',
        reason: 'All of the requirements are assessed.',
        reference_date: null,
        depends_on_projected_status: false,
        details: { requirements_assessment_status: 'complete' },
      },
      {
        rule_id: 'ELIG-CIT-001',
        requirement_id: 'req-1',
        status: 'needs_verification',
        reason: 'Citizenship requirement US cannot be confirmed from profile.',
        reference_date: null,
        depends_on_projected_status: false,
        details: null,
      },
      projectedEducation,
    ],
  },
  ...changes,
})
