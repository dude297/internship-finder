import { createContext, useContext } from 'react'

export type AuthState =
  | { status: 'loading' }
  // The session check couldn't get an answer (network error, 5xx, a proxy/wake-up page).
  // Auth is unknown, not anonymous: e.g. Render is still waking from sleep (ADR-009 §11).
  | { status: 'unavailable'; retrying: boolean }
  | { status: 'anonymous' }
  | { status: 'authenticated'; username: string }

export interface AuthContextValue {
  auth: AuthState
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  retrySession: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>')
  return value
}
