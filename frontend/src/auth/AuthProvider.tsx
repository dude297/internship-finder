import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, api, setCsrfToken, setUnauthorizedHandler } from '../api/client'
import type { SessionInfo } from '../api/schemas'
import { AuthContext, type AuthState } from './context'

// Automatic session re-checks while the backend is unreachable: about a minute in total, which
// covers a Render Free cold start. After that the user retries by hand.
const SESSION_RETRY_DELAYS_MS = [2000, 4000, 8000, 15000, 15000, 15000]

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
  const retryTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

  const supersede = useCallback(() => {
    generation.current += 1
    clearTimeout(retryTimer.current)
  }, [])

  const becomeAnonymous = useCallback(() => {
    supersede()
    setCsrfToken(null)
    setAuth({ status: 'anonymous' })
  }, [supersede])

  /**
   * Only a session response (or a 401) settles auth. Anything else (network error, 5xx, a
   * non-JSON wake-up page) means the backend is unavailable: show that and retry, but never
   * treat it as logged out.
   */
  const checkSession = useCallback(() => {
    supersede()
    const run = (attempt: number) => {
      const started = generation.current
      const apply = (next: () => AuthState) => {
        if (generation.current === started) setAuth(next())
      }
      api
        .getSession()
        .then((session) => apply(() => fromSession(session)))
        .catch((error: unknown) => {
          if (error instanceof ApiError && error.status === 401) {
            apply(() => ({ status: 'anonymous' }))
            return
          }
          const delay = SESSION_RETRY_DELAYS_MS[attempt]
          apply(() => ({ status: 'unavailable', retrying: delay !== undefined }))
          if (delay !== undefined && generation.current === started)
            retryTimer.current = setTimeout(() => run(attempt + 1), delay)
        })
    }
    run(0)
  }, [supersede])

  useEffect(() => {
    setUnauthorizedHandler(becomeAnonymous)
    checkSession()
    return supersede // unmounted: drop the in-flight check and any pending retry
  }, [becomeAnonymous, checkSession, supersede])

  const retrySession = useCallback(() => {
    setAuth({ status: 'loading' })
    checkSession()
  }, [checkSession])

  const login = useCallback(
    async (username: string, password: string) => {
      const session = await api.login(username, password)
      supersede()
      setAuth(fromSession(session))
    },
    [supersede],
  )

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

  const value = useMemo(
    () => ({ auth, login, logout, retrySession }),
    [auth, login, logout, retrySession],
  )
  return <AuthContext value={value}>{children}</AuthContext>
}
