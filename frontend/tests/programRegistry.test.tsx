import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { sourceSchema } from '../src/api/schemas'
import {
  detail,
  discoveryResponse,
  json,
  listPage,
  loggedIn,
  mockApi,
  renderAt,
  source,
  summary,
} from './helpers'

// Synthetic data only (ADR-014 §6: a typical window must never look like a deadline).

const registry = source({
  id: 'src-reg',
  kind: 'curated_registry',
  key: 'curated_registry:program-registry',
  identifier: 'program-registry',
  display_name: 'Curated Program Registry',
})
const smart = source({
  id: 'src-sr',
  kind: 'smartrecruiters',
  key: 'smartrecruiters:examplecompany',
  identifier: 'examplecompany',
  display_name: 'Example Company',
  builtin: false,
})

const windows = {
  program_cycle: '2027',
  typical_open_window: 'December–January',
  typical_close_window: 'mid-February',
}

describe('program registry', () => {
  it('parses the registry and a SmartRecruiters source', () => {
    expect(sourceSchema.parse(registry).kind).toBe('curated_registry')
    expect(sourceSchema.parse(smart).kind).toBe('smartrecruiters')
  })

  it('shows the registry like the built-in feed (no scope picker)', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [registry, smart],
    })
    renderAt('/sources')
    expect(await screen.findByText('Curated program registry')).toBeInTheDocument()
    expect(screen.getByText('examplecompany')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Import')).toHaveLength(2) // smart's picker + add form
  })

  it('submits a SmartRecruiters source without a region', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources/discovery': () => discoveryResponse(),
      'GET /api/sources': () => [registry],
      'POST /api/sources': () => json(smart, 201),
    })
    renderAt('/sources')
    fireEvent.change(await screen.findByLabelText('Provider'), {
      target: { value: 'smartrecruiters' },
    })
    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Example Company' },
    })
    fireEvent.change(screen.getByLabelText('Job board link or name'), {
      target: { value: 'https://jobs.smartrecruiters.com/ExampleCompany' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add source' }))
    await waitFor(() => expect(calls.at(-1)!.method).toBe('POST'))
    expect(calls.at(-1)!.body).toEqual({
      kind: 'smartrecruiters',
      display_name: 'Example Company',
      board: 'https://jobs.smartrecruiters.com/ExampleCompany',
      region: null,
      scope: 'internships_only',
    })
  })

  it('shows a typical window as unconfirmed, never as the deadline', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({
          ...windows,
          application_deadline: null,
          needs_date_verification: true,
          verify_by: '2041-01-15',
        }),
    })
    renderAt('/opportunities/opp-1')
    expect(await screen.findByText('No confirmed deadline')).toBeInTheDocument()
    expect(
      screen.getByText(/Typical application window: opens December–January/),
    ).toHaveTextContent(/closes mid-February \(not confirmed for 2027\)/)
    expect(screen.getByText(/Needs date verification/)).toHaveTextContent(/verify by/)
    expect(screen.getByText(/Application deadline:/).parentElement).not.toHaveTextContent(
      /February/,
    )
  })

  it('shows a verified deadline as the date', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () =>
        detail({ ...windows, application_deadline: '2041-02-01' }),
    })
    renderAt('/opportunities/opp-1')
    expect(await screen.findByText(/Application deadline:/)).toBeInTheDocument()
    expect(screen.queryByText('No confirmed deadline')).not.toBeInTheDocument()
    expect(screen.queryByText(/Needs date verification/)).not.toBeInTheDocument()
  })

  it('the date-verification filter and Upcoming programs preset set query params', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [registry],
      'GET /api/opportunities': () =>
        listPage([summary({ ...windows, application_deadline: null })]),
    })
    renderAt('/opportunities')
    expect(await screen.findByText('No confirmed deadline')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Date verification'), {
      target: { value: 'true' },
    })
    await waitFor(() =>
      expect(calls.at(-1)!.path).toMatch(/needs_date_verification=true/),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Upcoming programs' }))
    await waitFor(() => expect(calls.at(-1)!.path).toMatch(/source=src-reg/))
    expect(calls.at(-1)!.path).toMatch(/sort=deadline/)
  })
})
