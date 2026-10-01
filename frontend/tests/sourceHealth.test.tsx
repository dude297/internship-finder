import { fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { loggedIn, mockApi, renderAt, source } from './helpers'

// Synthetic sources only.

describe('source health', () => {
  it.each([
    ['never_run', 'Never run'],
    ['healthy', 'Healthy'],
    ['warning', 'Warning'],
    ['stale', 'Stale'],
    ['failing', 'Failing'],
    ['disabled', 'Disabled'],
  ])('shows the %s badge as "%s"', async (health, label) => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source({ health })],
    })
    renderAt('/sources')

    const item = await screen.findByRole('listitem')
    expect(within(item).getByText(new RegExp(`^!? ?${label}$`))).toBeInTheDocument()
  })

  it('shows consecutive failures and the last-success age without relying on color alone', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/sources': () => [
        source({
          health: 'failing',
          consecutive_failures: 3,
          last_success_at: '2040-09-20T12:00:00Z',
          last_success_age_hours: 240,
        }),
      ],
    })
    renderAt('/sources')

    const item = await screen.findByRole('listitem')
    expect(within(item).getByText('! Failing')).toBeInTheDocument()
    expect(within(item).getByText(/3 failed syncs in a row/)).toBeInTheDocument()
    expect(within(item).getByText(/240h ago/)).toBeInTheDocument()
  })

  it('adds an Ashby board by its link, with no region field', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/sources': () => [source()],
      'POST /api/sources': () =>
        source({
          id: 'src-ashby',
          kind: 'ashby',
          key: 'ashby:examplerobotics',
          identifier: 'examplerobotics',
          display_name: 'Example Robotics',
        }),
    })
    renderAt('/sources')

    fireEvent.change(await screen.findByLabelText('Provider'), {
      target: { value: 'ashby' },
    })
    expect(screen.queryByLabelText(/Lever region/)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Example Robotics' },
    })
    fireEvent.change(screen.getByLabelText('Job board link or name'), {
      target: { value: 'https://jobs.ashbyhq.com/examplerobotics' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add source' }))

    expect(await screen.findByText(/Added Example Robotics/)).toBeInTheDocument()
    expect(calls.at(-1)!.body).toEqual({
      kind: 'ashby',
      display_name: 'Example Robotics',
      board: 'https://jobs.ashbyhq.com/examplerobotics',
      region: null,
      scope: 'internships_only',
    })
  })
})
