import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import App from '../src/App'
import { json, loggedIn, mockApi, renderAt } from './helpers'

const savedProfile = {
  id: 'profile-1',
  updated_at: '2040-10-01T12:00:00Z',
  current_education_level: 'high_school',
  current_grade: '12',
  education_status_as_of: '2040-09-01',
  expected_graduation_date: '2041-06-10',
  expected_enrollment_date: '2041-08-25',
  expected_future_education_level: 'undergraduate',
  date_of_birth: null,
  citizenships: ['US', 'CA'],
  work_authorizations: null,
  location: null,
}

const noProfile = () => json({ detail: 'No profile yet.' }, 404)

describe('profile editor', () => {
  it('starts empty before a profile exists and explains optional fields', async () => {
    mockApi({ ...loggedIn, 'GET /api/profile': noProfile })
    renderAt('/profile')

    expect(await screen.findByLabelText('Current level')).toHaveValue('')
    expect(
      screen.getByRole('group', { name: 'Education transition' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/These are optional/)).toBeInTheDocument()
  })

  it('saves normalized values with the CSRF token and confirms re-evaluation', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/profile': noProfile,
      'PUT /api/profile': () => ({ profile: savedProfile, reevaluated_opportunities: 2 }),
    })
    renderAt('/profile')
    fireEvent.change(await screen.findByLabelText('Current level'), {
      target: { value: 'high_school' },
    })
    fireEvent.change(screen.getByLabelText('Status as of'), {
      target: { value: '2040-09-01' },
    })
    fireEvent.change(screen.getByLabelText('Citizenship(s) (optional)'), {
      target: { value: 'us, ca' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Profile saved. Eligibility results updated.',
    )
    const put = calls.find((c) => c.method === 'PUT')
    expect(put?.headers['X-CSRF-Token']).toBe('synthetic-csrf')
    expect(put?.body).toMatchObject({
      current_education_level: 'high_school',
      education_status_as_of: '2040-09-01',
      citizenships: ['US', 'CA'],
      date_of_birth: null,
      location: null,
    })
    expect(screen.getByLabelText('Citizenship(s) (optional)')).toHaveValue('US, CA')
  })

  it('shows backend validation errors next to the field', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/profile': () => savedProfile,
      'PUT /api/profile': () =>
        json(
          {
            detail: [
              {
                loc: ['body', 'citizenships', 0],
                msg: 'Value error, UK is not an ISO 3166-1 alpha-2 country code',
                type: 'value_error',
              },
            ],
          },
          422,
        ),
    })
    renderAt('/profile')
    const citizenship = await screen.findByLabelText('Citizenship(s) (optional)')
    fireEvent.change(citizenship, { target: { value: 'UK' } })

    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))

    expect(
      await screen.findByText('UK is not an ISO 3166-1 alpha-2 country code'),
    ).toBeInTheDocument()
    expect(citizenship).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Please correct the highlighted fields.',
    )
  })

  it('shows a model-level validation error', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/profile': noProfile,
      'PUT /api/profile': () =>
        json(
          {
            detail: [
              {
                loc: ['body'],
                msg: 'Value error, current_education_level and education_status_as_of must be set together',
                type: 'value_error',
              },
            ],
          },
          422,
        ),
    })
    renderAt('/profile')
    fireEvent.click(await screen.findByRole('button', { name: 'Save profile' }))

    expect(
      await screen.findByText(/must be set together/, { selector: '[role=alert]' }),
    ).toBeInTheDocument()
  })

  it('ignores a stale response from a superseded load (regression)', async () => {
    // StrictMode runs the load effect twice. The first response must not render a form that
    // the second response would then overwrite while the user is typing.
    let finishSecond: (response: Response) => void = () => {}
    let loads = 0
    mockApi({
      ...loggedIn,
      'GET /api/profile': () => {
        loads += 1
        if (loads === 1) return { ...savedProfile, location: 'Stale City' }
        return new Promise<Response>((resolve) => (finishSecond = resolve))
      },
    })
    render(
      <StrictMode>
        <MemoryRouter initialEntries={['/profile']}>
          <App />
        </MemoryRouter>
      </StrictMode>,
    )
    await waitFor(() => expect(loads).toBe(2))
    await new Promise((resolve) => setTimeout(resolve, 50)) // let the stale response settle
    expect(screen.getByText('Loading profile…')).toBeInTheDocument()
    expect(screen.queryByLabelText('Location (optional)')).not.toBeInTheDocument()

    finishSecond(json({ ...savedProfile, location: 'Current City' }))

    expect(await screen.findByLabelText('Location (optional)')).toHaveValue(
      'Current City',
    )
  })

  it('defaults every work-authorization answer to "not provided" and saves explicit answers', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/profile': () => savedProfile,
      'PUT /api/profile': () => ({ profile: savedProfile, reevaluated_opportunities: 0 }),
    })
    renderAt('/profile')
    const group = await screen.findByRole('group', { name: 'Work authorization' })
    expect(group).toBeInTheDocument()
    const labels = [
      'Currently authorized to work in the U.S.',
      'Need employer sponsorship now',
      'May need sponsorship in the future',
      'U.S. citizen',
      'U.S. permanent resident (green card holder)',
      'U.S. person for export control (ITAR/EAR)',
      'Hold an active U.S. security clearance',
    ]
    for (const label of labels) {
      const select = screen.getByLabelText(label)
      expect(select).toHaveValue('')
      expect(select).toHaveDisplayValue('Prefer not to say / not provided')
    }
    expect(screen.getByText(/protected individual/)).toBeInTheDocument()

    // Citizen "yes" must not fill in any other answer.
    fireEvent.change(screen.getByLabelText('U.S. citizen'), { target: { value: 'yes' } })
    fireEvent.change(screen.getByLabelText('Need employer sponsorship now'), {
      target: { value: 'no' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))
    await screen.findByRole('status')

    const put = calls.find((c) => c.method === 'PUT')
    expect(put?.body).toMatchObject({
      us_citizen: true,
      needs_sponsorship_now: false,
      work_authorized_us: null,
      us_person_export_control: null,
      us_permanent_resident: null,
      needs_sponsorship_future: null,
      active_security_clearance: null,
    })
  })

  it('shows previously saved work-authorization answers', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/profile': () => ({
        ...savedProfile,
        us_person_export_control: false,
        work_authorized_us: true,
      }),
    })
    renderAt('/profile')

    expect(
      await screen.findByLabelText('U.S. person for export control (ITAR/EAR)'),
    ).toHaveValue('no')
    expect(screen.getByLabelText('Currently authorized to work in the U.S.')).toHaveValue(
      'yes',
    )
    expect(screen.getByLabelText('U.S. citizen')).toHaveValue('')
  })
})
