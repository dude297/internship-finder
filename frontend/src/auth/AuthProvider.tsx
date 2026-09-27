import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setCsrfToken, setUnauthorizedHandler } from '../api/client'
import type { SessionInfo } from '../api/schemas'
import { AuthContext, type AuthState } from './context'

function fromSession(session: SessionInfo): AuthState {
  setCsrfToken(session.authenticated ? session.csrf_token : null)
  return session.authenticated && session.username
    ? { status: 'authenticated', username: session.username }
    : { status: 'anonymous' }
}

/** Auth state comes from the server session (GET /api/auth/session), never browser storage. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' })

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setCsrfToken(null)
      setAuth({ status: 'anonymous' })
    })
    let active = true
    api
      .getSession()
      .then((session) => active && setAuth(fromSession(session)))
      .catch(() => active && setAuth({ status: 'anonymous' }))
    return () => {
      active = false
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    setAuth(fromSession(await api.login(username, password)))
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setCsrfToken(null)
      setAuth({ status: 'anonymous' })
    }
  }, [])

  const value = useMemo(() => ({ auth, login, logout }), [auth, login, logout])
  return <AuthContext value={value}>{children}</AuthContext>
}
