import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { dashboard, json, loggedIn, loggedOut, mockApi, renderAt } from './helpers'

function submit() {
  fireEvent.change(screen.getByLabelText('Username'), {
    target: { value: 'synthetic-owner' },
  })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
  fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
}

describe('landing page', () => {
  it('renders for logged-out visitors with a sign-in link and no extra requests', async () => {
    const calls = mockApi(loggedOut)
    renderAt('/')
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: /internships that actually fit you/i,
      }),
    ).toBeInTheDocument()
    for (const n of ['01', '02', '03', '04', '05'])
      expect(screen.getByText(n)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /seven source types/i })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Sign in' })[0]).toHaveAttribute(
      'href',
      '/login',
    )
    // Only the shared session check: the page itself makes no API calls.
    await act(async () => {})
    expect(calls.map((c) => c.path)).toEqual(['/api/auth/session'])
  })

  it('sends a signed-in owner to the app', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/dashboard': () => dashboard(),
    })
    renderAt('/')
    expect(
      await screen.findByRole('heading', {
        name: /^(Hello|Good (morning|afternoon|evening))$/,
      }),
    ).toBeInTheDocument()
  })
})

describe('login states', () => {
  afterEach(() => vi.useRealTimers())

  it('explains a rate limit and keeps the form usable', async () => {
    mockApi({
      ...loggedOut,
      'POST /api/auth/login': () =>
        json({ detail: 'Too many attempts. Try again later.' }, 429),
    })
    renderAt('/login')
    await screen.findByRole('form', { name: 'Log in' })
    submit()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Too many attempts')
    expect(alert).toHaveTextContent('Try again later.')
    expect(screen.getByLabelText('Password')).toHaveAttribute(
      'aria-describedby',
      'login-error',
    )
    expect(screen.getByRole('button', { name: 'Log in' })).toBeEnabled()
  })

  it('marks the password invalid on wrong credentials', async () => {
    mockApi({
      ...loggedOut,
      'POST /api/auth/login': () =>
        json({ detail: 'Invalid username or password.' }, 401),
    })
    renderAt('/login')
    await screen.findByRole('form', { name: 'Log in' })
    submit()
    await screen.findByRole('alert')
    expect(screen.getByLabelText('Password')).toHaveAttribute('aria-invalid', 'true')
  })

  it('shows the unavailable message on a network failure', async () => {
    mockApi({
      ...loggedOut,
      'POST /api/auth/login': () => Promise.reject(new TypeError('Failed to fetch')),
    })
    renderAt('/login')
    await screen.findByRole('form', { name: 'Log in' })
    submit()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Couldn't reach the server. Try again.",
    )
    expect(screen.getByRole('button', { name: 'Log in' })).toBeEnabled()
  })

  it('shows a waking notice when the session check is slow', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => {})),
    )
    renderAt('/login')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(4500))
    expect(screen.getByRole('status')).toHaveTextContent('Waking the server')
  })

  it('shows a waking notice when the login request is slow', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockApi({ ...loggedOut, 'POST /api/auth/login': () => new Promise(() => {}) })
    renderAt('/login')
    await screen.findByRole('form', { name: 'Log in' })
    submit()
    await act(() => vi.advanceTimersByTimeAsync(4500))
    expect(screen.getByRole('status')).toHaveTextContent('Waking the server')
  })

  it('offers Retry once automatic retries are exhausted', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    mockApi({ 'GET /api/auth/session': () => json({ detail: 'Bad Gateway' }, 502) })
    renderAt('/login')
    await act(() => vi.advanceTimersByTimeAsync(120_000))
    expect(screen.getByRole('status')).toHaveTextContent(
      "Can't reach the server right now.",
    )
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
