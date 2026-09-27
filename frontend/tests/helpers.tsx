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
 * Stub fetch with handlers keyed by "METHOD /api/path". A handler returns a Response, a JSON
 * body, or a Promise (returned as is). Unhandled requests fail the test loudly. Returns the recorded calls.
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
        body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
        headers: (init.headers ?? {}) as Record<string, string>,
      }
      calls.push(call)
      const handler = handlers[`${method} ${input}`]
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
  requirements_assessment_status: 'complete',
  eligibility_status: 'eligible',
  evaluated_at: '2040-10-01T12:00:00Z',
  application_status: null,
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
