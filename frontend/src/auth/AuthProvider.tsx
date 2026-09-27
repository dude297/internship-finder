import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, api, setCsrfToken, setUnauthorizedHandler } from '../api/client'
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
  // Bumped by every completed auth transition (login, logout, session loss). A session check
  // started under an older generation is stale and must not overwrite the newer state.
  const generation = useRef(0)

  const becomeAnonymous = useCallback(() => {
    generation.current += 1
    setCsrfToken(null)
    setAuth({ status: 'anonymous' })
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(becomeAnonymous)
    const started = generation.current
    const apply = (next: () => AuthState) => {
      if (generation.current === started) setAuth(next())
    }
    api
      .getSession()
      .then((session) => apply(() => fromSession(session)))
      .catch(() => apply(() => ({ status: 'anonymous' })))
    return () => {
      generation.current += 1 // unmounted: drop the in-flight check
    }
  }, [becomeAnonymous])

  const login = useCallback(async (username: string, password: string) => {
    const session = await api.login(username, password)
    generation.current += 1
    setAuth(fromSession(session))
  }, [])

  /**
   * Only drops local auth state once the server confirmed the session is gone (204), or it was
   * already unusable (401, handled by the unauthorized handler). Any other failure rethrows and
   * leaves the user signed in: the session and its cookie may still be valid.
   */
  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return
      throw error
    }
    becomeAnonymous()
  }, [becomeAnonymous])

  const value = useMemo(() => ({ auth, login, logout }), [auth, login, logout])
  return <AuthContext value={value}>{children}</AuthContext>
}
