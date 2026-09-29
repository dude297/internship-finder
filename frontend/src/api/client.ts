import { z } from 'zod'
import {
  applicationSchema,
  evaluationSchema,
  matchProfileSaveSchema,
  matchProfileSchema,
  opportunityDetailSchema,
  opportunityPageSchema,
  profileSaveSchema,
  profileSchema,
  runSchema,
  sessionSchema,
  sourceSchema,
  type ApplicationInput,
  type MatchProfile,
  type OpportunityInput,
  type OpportunityQuery,
  type ProfileInput,
  type SourceInput,
  type SourceScope,
} from './schemas'

// The only place that talks to the backend. Requests are same-origin (/api, proxied by Vite in
// development), so the HttpOnly session cookie is sent automatically and never touches JS.

export interface FieldIssue {
  field: string | null
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly issues: FieldIssue[]

  constructor(status: number, message: string, issues: FieldIssue[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.issues = issues
  }
}

// CSRF token for unsafe requests (ADR-007 §5). In memory only, never in browser storage.
let csrfToken: string | null = null
let onUnauthorized: () => void = () => {}

export function setCsrfToken(token: string | null) {
  csrfToken = token
}

/** Called when any request (other than login) gets a 401, e.g. an expired session. */
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

const validationIssue = z.object({
  loc: z.array(z.union([z.string(), z.number()])),
  msg: z.string(),
})
const errorBody = z.object({ detail: z.union([z.string(), z.array(validationIssue)]) })

function toIssue(issue: z.infer<typeof validationIssue>): FieldIssue {
  // loc is ["body", field, ...]; a model-level error has no field.
  const field =
    issue.loc[0] === 'body' && typeof issue.loc[1] === 'string' ? issue.loc[1] : null
  const message = issue.msg.replace(/^Value error, /, '')
  const index = issue.loc[2]
  return {
    field,
    message:
      field === 'requirements' && typeof index === 'number'
        ? `Requirement ${index + 1}: ${message}`
        : message,
  }
}

async function toError(response: Response): Promise<ApiError> {
  const parsed = errorBody.safeParse(await response.json().catch(() => undefined))
  if (!parsed.success)
    return new ApiError(response.status, `Request failed (HTTP ${response.status})`)
  const { detail } = parsed.data
  if (typeof detail === 'string') return new ApiError(response.status, detail)
  return new ApiError(
    response.status,
    'Please correct the highlighted fields.',
    detail.map(toIssue),
  )
}

async function request<T>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  path: string,
  schema: z.ZodType<T> | null,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login') onUnauthorized()
    throw await toError(response)
  }
  if (schema === null) return undefined as T

  const parsed = schema.safeParse(await response.json().catch(() => undefined))
  if (!parsed.success)
    throw new ApiError(response.status, 'The server sent an unexpected response.')
  return parsed.data
}

export const api = {
  getSession: () => request('GET', '/auth/session', sessionSchema),
  login: (username: string, password: string) =>
    request('POST', '/auth/login', sessionSchema, { username, password }),
  logout: () => request('POST', '/auth/logout', null),

  /** The profile, or null before it has been created. */
  getProfile: () =>
    request('GET', '/profile', profileSchema).catch((error: unknown) => {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }),
  saveProfile: (profile: ProfileInput) =>
    request('PUT', '/profile', profileSaveSchema, profile),
  getMatchProfile: () => request('GET', '/profile/match', matchProfileSchema),
  /** Saves everything at once; the backend rescores the catalog in the same request. */
  saveMatchProfile: (body: MatchProfile) =>
    request('PUT', '/profile/match', matchProfileSaveSchema, body),

  listOpportunities: (query: OpportunityQuery) => {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== '') params.set(key, String(value))
    return request('GET', `/opportunities?${params}`, opportunityPageSchema)
  },
  getOpportunity: (id: string) =>
    request('GET', `/opportunities/${encodeURIComponent(id)}`, opportunityDetailSchema),
  createOpportunity: (body: OpportunityInput) =>
    request('POST', '/opportunities', opportunityDetailSchema, body),
  updateOpportunity: (id: string, body: OpportunityInput) =>
    request(
      'PUT',
      `/opportunities/${encodeURIComponent(id)}`,
      opportunityDetailSchema,
      body,
    ),
  deleteOpportunity: (id: string) =>
    request('DELETE', `/opportunities/${encodeURIComponent(id)}`, null),
  evaluateOpportunity: (id: string) =>
    request(
      'POST',
      `/opportunities/${encodeURIComponent(id)}/evaluate`,
      evaluationSchema,
    ),

  saveApplication: (opportunityId: string, body: ApplicationInput) =>
    request(
      'PUT',
      `/opportunities/${encodeURIComponent(opportunityId)}/application`,
      applicationSchema,
      body,
    ),
  deleteApplication: (opportunityId: string) =>
    request(
      'DELETE',
      `/opportunities/${encodeURIComponent(opportunityId)}/application`,
      null,
    ),

  listSources: () => request('GET', '/sources', z.array(sourceSchema)),
  createSource: (body: SourceInput) => request('POST', '/sources', sourceSchema, body),
  updateSource: (
    id: string,
    body: { display_name: string; enabled: boolean; scope?: SourceScope },
  ) => request('PUT', `/sources/${encodeURIComponent(id)}`, sourceSchema, body),
  syncSource: (id: string) =>
    request('POST', `/sources/${encodeURIComponent(id)}/sync`, runSchema),
  syncAllSources: () => request('POST', '/sources/sync', z.array(runSchema)),
}
