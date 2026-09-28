import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { json, listPage, loggedIn, loggedOut, mockApi, renderAt } from './helpers'

function fillLogin(username: string, password: string) {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: username } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
}

describe('authentication', () => {
  it('shows a loading state while the session is checked', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => {})),
    )
    renderAt('/opportunities')
    expect(screen.getByRole('status')).toHaveTextContent('Loading…')
  })

  it('redirects protected pages to the login form', async () => {
    mockApi(loggedOut)
    renderAt('/profile')
    expect(await screen.findByRole('form', { name: 'Log in' })).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password')
    expect(screen.queryByText(/register|sign up|forgot/i)).not.toBeInTheDocument()
  })

  it('logs in and returns to the requested page', async () => {
    const calls = mockApi({
      ...loggedOut,
      'POST /api/auth/login': () => ({
        authenticated: true,
        username: 'synthetic-owner',
        csrf_token: 'synthetic-csrf',
      }),
      'GET /api/opportunities': () => listPage([]),
    })
    renderAt('/opportunities')
    await screen.findByRole('form', { name: 'Log in' })

    fillLogin('synthetic-owner', 'synthetic-password')

    expect(
      await screen.findByRole('heading', { name: 'Opportunities' }),
    ).toBeInTheDocument()
    const login = calls.find((c) => c.path === '/api/auth/login')
    expect(login?.body).toEqual({
      username: 'synthetic-owner',
      password: 'synthetic-password',
    })
  })

  it('shows the generic failure message and re-enables the form', async () => {
    mockApi({
      ...loggedOut,
      'POST /api/auth/login': () =>
        json({ detail: 'Invalid username or password.' }, 401),
    })
    renderAt('/login')
    await screen.findByRole('form', { name: 'Log in' })

    fillLogin('synthetic-owner', 'wrong-password')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Invalid username or password.',
    )
    expect(screen.getByRole('button', { name: 'Log in' })).toBeEnabled()
  })

  it('shows a loading label while logging in', async () => {
    mockApi({
      ...loggedOut,
      'POST /api/auth/login': () => new Promise(() => {}),
    })
    renderAt('/login')
    await screen.findByRole('form', { name: 'Log in' })

    fillLogin('synthetic-owner', 'synthetic-password')

    expect(await screen.findByRole('button', { name: 'Logging in…' })).toBeDisabled()
  })

  it('logs out with the CSRF token and returns to login', async () => {
    const calls = mockApi({
      ...loggedIn,
      'GET /api/opportunities': () => listPage([]),
      'POST /api/auth/logout': () => new Response(null, { status: 204 }),
    })
    renderAt('/opportunities')
    fireEvent.click(await screen.findByRole('button', { name: 'Log out' }))

    expect(await screen.findByRole('form', { name: 'Log in' })).toBeInTheDocument()
    const logout = calls.find((c) => c.path === '/api/auth/logout')
    expect(logout?.headers['X-CSRF-Token']).toBe('synthetic-csrf')
  })

  it('ignores a session check that resolves after a newer login', async () => {
    let resolveSession: (response: Response) => void = () => {}
    mockApi({
      'GET /api/auth/session': () =>
        new Promise<Response>((resolve) => {
          resolveSession = resolve
        }),
      'POST /api/auth/login': () => ({
        authenticated: true,
        username: 'synthetic-owner',
        csrf_token: 'synthetic-csrf',
      }),
      'GET /api/opportunities': () => listPage([]),
    })
    renderAt('/login')

    fillLogin('synthetic-owner', 'synthetic-password')
    expect(
      await screen.findByRole('heading', { name: 'Opportunities' }),
    ).toBeInTheDocument()

    // The initial, pre-login check finally answers "anonymous": it must not log us out.
    await act(async () => {
      resolveSession(json({ authenticated: false, username: null, csrf_token: null }))
      await Promise.resolve()
    })
    expect(screen.getByRole('heading', { name: 'Opportunities' })).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Log in' })).not.toBeInTheDocument()
  })

  it.each([
    ['a network failure', () => Promise.reject(new TypeError('Failed to fetch'))],
    ['HTTP 500', () => json({ detail: 'Internal Server Error' }, 500)],
  ])('stays signed in when logout fails with %s', async (_label, failure) => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities': () => listPage([]),
      'POST /api/auth/logout': failure,
    })
    renderAt('/opportunities')
    fireEvent.click(await screen.findByRole('button', { name: 'Log out' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Couldn't log out. You're still signed in.",
    )
    expect(screen.getByRole('heading', { name: 'Opportunities' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Log out' })).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Log in' })).not.toBeInTheDocument()
  })

  it('keeps the CSRF token after a failed logout so a retry can succeed', async () => {
    let attempts = 0
    const calls = mockApi({
      ...loggedIn,
      'GET /api/opportunities': () => listPage([]),
      'POST /api/auth/logout': () =>
        ++attempts === 1
          ? json({ detail: 'Internal Server Error' }, 500)
          : new Response(null, { status: 204 }),
    })
    renderAt('/opportunities')
    fireEvent.click(await screen.findByRole('button', { name: 'Log out' }))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Log out' }))

    expect(await screen.findByRole('form', { name: 'Log in' })).toBeInTheDocument()
    const logouts = calls.filter((c) => c.path === '/api/auth/logout')
    expect(logouts.map((c) => c.headers['X-CSRF-Token'])).toEqual([
      'synthetic-csrf',
      'synthetic-csrf',
    ])
  })

  it('treats logout of an already-invalid session (401) as logged out', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities': () => listPage([]),
      'POST /api/auth/logout': () => json({ detail: 'Not authenticated.' }, 401),
    })
    renderAt('/opportunities')
    fireEvent.click(await screen.findByRole('button', { name: 'Log out' }))

    expect(await screen.findByRole('form', { name: 'Log in' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('returns to login when the session expires mid-use', async () => {
    mockApi({
      ...loggedIn,
      'GET /api/opportunities': () => json({ detail: 'Not authenticated.' }, 401),
    })
    renderAt('/opportunities')

    expect(await screen.findByRole('form', { name: 'Log in' })).toBeInTheDocument()
  })

  it('never stores auth state in browser storage', async () => {
    mockApi({ ...loggedIn, 'GET /api/opportunities': () => listPage([]) })
    renderAt('/opportunities')
    await screen.findByRole('heading', { name: 'Opportunities' })

    await waitFor(() => {
      expect(localStorage.length).toBe(0)
      expect(sessionStorage.length).toBe(0)
    })
  })

  describe('when the backend is unavailable (e.g. Render waking up)', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    const html = (status: number) =>
      new Response('<html>Service waking up</html>', {
        status,
        headers: { 'Content-Type': 'text/html' },
      })

    it.each([
      ['a network error', () => Promise.reject(new TypeError('Failed to fetch'))],
      ['HTTP 502', () => json({ detail: 'Bad Gateway' }, 502)],
      ['an HTML 503 page', () => html(503)],
      ['a non-JSON 200 page', () => html(200)],
    ])('shows a waking state, not the login form, on %s', async (_label, failure) => {
      mockApi({ 'GET /api/auth/session': failure })
      renderAt('/opportunities')

      expect(await screen.findByText(/Server is waking up…/)).toHaveAttribute(
        'role',
        'status',
      )
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
      expect(screen.queryByRole('form', { name: 'Log in' })).not.toBeInTheDocument()
    })

    it('restores the existing session on Retry', async () => {
      let up = false
      const calls = mockApi({
        'GET /api/auth/session': () =>
          up ? loggedIn['GET /api/auth/session']() : json({ detail: 'Bad Gateway' }, 502),
        'GET /api/opportunities': () => listPage([]),
        'POST /api/auth/logout': () => new Response(null, { status: 204 }),
      })
      renderAt('/opportunities')
      await screen.findByText(/Server is waking up/)

      up = true
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

      expect(
        await screen.findByRole('heading', { name: 'Opportunities' }),
      ).toBeInTheDocument()
      // The CSRF token from the recovered session is used (memory only).
      fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
      await screen.findByRole('form', { name: 'Log in' })
      const logout = calls.find((c) => c.path === '/api/auth/logout')
      expect(logout?.headers['X-CSRF-Token']).toBe('synthetic-csrf')
    })

    it('retries automatically and recovers once the server is up', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      let attempts = 0
      mockApi({
        'GET /api/auth/session': () =>
          ++attempts < 3
            ? json({ detail: 'Service Unavailable' }, 503)
            : loggedIn['GET /api/auth/session'](),
        'GET /api/opportunities': () => listPage([]),
      })
      renderAt('/opportunities')
      await screen.findByText(/Server is waking up/)

      await act(() => vi.advanceTimersByTimeAsync(2000 + 4000))

      expect(
        await screen.findByRole('heading', { name: 'Opportunities' }),
      ).toBeInTheDocument()
      expect(attempts).toBe(3)
    })

    it('stops retrying after about a minute but keeps a Retry button', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      let attempts = 0
      mockApi({
        'GET /api/auth/session': () => {
          attempts += 1
          return json({ detail: 'Bad Gateway' }, 502)
        },
      })
      renderAt('/opportunities')
      await screen.findByText(/Server is waking up/)

      await act(() => vi.advanceTimersByTimeAsync(120_000))

      expect(
        await screen.findByText("Can't reach the server right now."),
      ).toHaveAttribute('role', 'status')
      expect(attempts).toBe(7) // the first check plus six retries
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    })

    it('treats a 401 from the session check as logged out', async () => {
      mockApi({
        'GET /api/auth/session': () => json({ detail: 'Not authenticated.' }, 401),
      })
      renderAt('/opportunities')

      expect(await screen.findByRole('form', { name: 'Log in' })).toBeInTheDocument()
    })

    it('does not let a pending retry overwrite a newer login', async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true })
      let sessionChecks = 0
      mockApi({
        'GET /api/auth/session': () => {
          sessionChecks += 1
          return json({ detail: 'Bad Gateway' }, 502)
        },
        'POST /api/auth/login': () => ({
          authenticated: true,
          username: 'synthetic-owner',
          csrf_token: 'synthetic-csrf',
        }),
        'GET /api/opportunities': () => listPage([]),
      })
      renderAt('/login')
      await waitFor(() => expect(sessionChecks).toBe(1))

      fillLogin('synthetic-owner', 'synthetic-password')
      await screen.findByRole('heading', { name: 'Opportunities' })
      await act(() => vi.advanceTimersByTimeAsync(120_000))

      expect(sessionChecks).toBe(1)
      expect(screen.getByRole('heading', { name: 'Opportunities' })).toBeInTheDocument()
    })
  })
})
