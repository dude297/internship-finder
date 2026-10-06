import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { detail, listPage, loggedIn, mockApi, renderAt, summary } from './helpers'

const noSources = { 'GET /api/sources': () => [] }
const imported = { origin: 'imported' as const, manually_curated_at: null }
const curated = {
  origin: 'imported' as const,
  manually_curated_at: '2041-01-02T00:00:00Z',
}

afterEach(() => vi.restoreAllMocks())

describe('hide and unhide', () => {
  it('hides with the CSRF token and then offers Unhide', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(imported),
      'PUT /api/opportunities/opp-1/dismissal': () =>
        detail({ ...imported, dismissed_at: '2041-01-02T00:00:00Z' }),
      'DELETE /api/opportunities/opp-1/dismissal': () => detail(imported),
    })
    renderAt('/opportunities/opp-1')

    fireEvent.click(await screen.findByRole('button', { name: 'Hide' }))
    expect(await screen.findByRole('button', { name: 'Unhide' })).toBeInTheDocument()
    expect(screen.getByText(/Hidden: not shown in your list/)).toBeInTheDocument()
    const put = calls.find((c) => c.method === 'PUT' && c.path.endsWith('/dismissal'))
    expect(put?.headers['X-CSRF-Token']).toBe('synthetic-csrf')
    expect(put?.body).toEqual({ reason: 'not_interested' })

    fireEvent.click(screen.getByRole('button', { name: 'Unhide' }))
    expect(await screen.findByRole('button', { name: 'Hide' })).toBeInTheDocument()
  })

  it('warns that deleting an imported opportunity brings it back on sync', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockApi({ ...loggedIn, 'GET /api/opportunities/opp-1': () => detail(imported) })
    renderAt('/opportunities/opp-1')

    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('use Hide'))
  })

  it('sends the hidden filter and marks hidden rows', async () => {
    const calls = mockApi({
      ...loggedIn,
      ...noSources,
      'GET /api/opportunities': () =>
        listPage([
          summary({
            id: 'h1',
            title: 'Hidden One',
            dismissed_at: '2041-01-02T00:00:00Z',
          }),
        ]),
    })
    renderAt('/opportunities?hidden=only')

    expect(await screen.findByText('Hidden One')).toBeInTheDocument()
    expect(screen.getAllByText('Hidden').length).toBeGreaterThan(0)
    expect(calls.some((c) => c.path.includes('hidden=only'))).toBe(true)
    expect(
      calls.some((c) => c.path.includes('hidden=') && !c.path.includes('only')),
    ).toBe(false)
  })
})

describe('revert to source', () => {
  it('is offered only for curated imported opportunities and needs confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const calls = mockApi({
      ...loggedIn,
      'GET /api/opportunities/opp-1': () => detail(curated),
      'POST /api/opportunities/opp-1/revert-to-source': () => detail(imported),
    })
    renderAt('/opportunities/opp-1')

    const button = await screen.findByRole('button', { name: 'Revert to source' })
    fireEvent.click(button)
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('discards your edits'))
    expect(calls.some((c) => c.path.endsWith('/revert-to-source'))).toBe(false)

    confirm.mockReturnValue(true)
    fireEvent.click(button)
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Revert to source' })).toBeNull(),
    )
    expect(calls.find((c) => c.path.endsWith('/revert-to-source'))?.method).toBe('POST')
  })

  it('is not offered for manual or uncurated opportunities', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities/m1': () =>
        detail({ origin: 'manual', manually_curated_at: '2041-01-02T00:00:00Z' }),
    })
    renderAt('/opportunities/m1')

    await screen.findByRole('button', { name: 'Hide' })
    expect(screen.queryByRole('button', { name: 'Revert to source' })).toBeNull()
  })
})
