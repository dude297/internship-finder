import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/context'
import { Mark } from '../components/Mark'

// How long a session check or a login may take before we explain that Render may be waking up.
const WAKING_AFTER_MS = 4000

type LoginError = { kind: 'credentials' | 'rate-limit' | 'unavailable'; message: string }

const inputClass =
  'mt-1 block min-h-11 w-full rounded-control border border-lab-border bg-lab-bg px-3 text-lab-text placeholder:text-lab-muted disabled:opacity-60'

/** True once `active` has stayed true for `ms`. */
function useDelayed(active: boolean, ms: number) {
  const [elapsed, setElapsed] = useState(false)
  useEffect(() => {
    if (!active) return
    const timer = setTimeout(() => setElapsed(true), ms)
    return () => {
      clearTimeout(timer)
      setElapsed(false)
    }
  }, [active, ms])
  return active && elapsed
}

function SystemGraphic() {
  const rows = [
    ['session', 'httpOnly cookie, same-origin'],
    ['csrf', 'token held in memory only'],
    ['scoring', 'deterministic rules'],
    ['access', 'single owner, no public accounts'],
  ]
  return (
    <div className="mt-10 hidden md:block">
      <svg
        viewBox="0 0 320 96"
        fill="none"
        aria-hidden="true"
        className="h-auto w-full max-w-sm"
      >
        <g stroke="var(--color-lab-border)" strokeWidth="1.5">
          <path d="M40 48H110M130 48H190M210 48H280" />
        </g>
        <g stroke="var(--color-lab-accent)" strokeWidth="2" strokeLinecap="round">
          <path d="M40 48H110M130 48H190M210 48H280" className="lab-signal" />
        </g>
        <g
          fill="var(--color-lab-elevated)"
          stroke="var(--color-lab-accent)"
          strokeWidth="1.5"
        >
          <rect x="20" y="34" width="28" height="28" rx="3" />
          <rect x="110" y="30" width="36" height="36" rx="3" />
          <rect x="190" y="34" width="28" height="28" rx="3" />
          <rect x="272" y="34" width="28" height="28" rx="3" />
        </g>
      </svg>
      <dl className="mt-6 space-y-2 font-mono text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="flex gap-3">
            <dt className="w-16 shrink-0 text-lab-accent">{k}</dt>
            <dd className="text-lab-muted">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

export function LoginPage() {
  const { auth, login, retrySession } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<LoginError | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const checkingSlow = useDelayed(auth.status === 'loading', WAKING_AFTER_MS)
  const submittingSlow = useDelayed(submitting, WAKING_AFTER_MS)

  const from = (location.state as { from?: string } | null)?.from ?? '/opportunities'
  if (auth.status === 'authenticated') return <Navigate to={from} replace />

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setSubmitting(true)
    setError(null)
    try {
      await login(String(form.get('username') ?? ''), String(form.get('password') ?? ''))
      navigate(from, { replace: true })
    } catch (caught) {
      if (caught instanceof ApiError && (caught.status === 401 || caught.status === 429))
        setError({
          kind: caught.status === 429 ? 'rate-limit' : 'credentials',
          message: caught.message,
        })
      else
        setError({
          kind: 'unavailable',
          message: "Couldn't reach the server. Try again.",
        })
      setSubmitting(false)
    }
  }

  // Auth is unknown (not logged out) while the session check is slow or failing.
  const wakingNotice =
    submittingSlow || checkingSlow || auth.status === 'unavailable'
      ? auth.status === 'unavailable' && !auth.retrying
        ? "Can't reach the server right now."
        : 'Waking the server… The free host sleeps when idle, so this can take up to a minute.'
      : null
  const errorTitle = {
    credentials: 'Sign-in failed',
    'rate-limit': 'Too many attempts',
    unavailable: 'Server unavailable',
  }
  const describedBy = error ? 'login-error' : undefined

  return (
    <div className="grid min-h-screen bg-lab-bg font-sans text-lab-text md:grid-cols-2">
      <aside className="border-b border-lab-border bg-lab-surface px-gutter py-8 md:border-r md:border-b-0 md:p-12">
        <Link to="/" className="inline-flex min-h-10 items-center gap-3">
          <Mark className="h-8 w-8 text-lab-accent" />
          <span className="font-semibold">Internship Finder</span>
        </Link>
        <p className="mt-8 font-mono text-xs tracking-widest text-lab-accent uppercase md:mt-16">
          Private workspace
        </p>
        <p className="mt-3 max-w-sm text-2xl font-semibold tracking-tight md:text-3xl">
          Eligibility first. Fit with reasons. Nothing sent without you.
        </p>
        <SystemGraphic />
      </aside>

      <main className="lab-rise flex items-center px-gutter py-10 md:p-12">
        <div className="mx-auto w-full max-w-sm">
          <h1 className="text-2xl font-semibold">Sign in</h1>
          <div aria-live="polite" className="min-h-0">
            {wakingNotice && (
              <p
                role="status"
                className="mt-4 flex items-start gap-3 rounded-control border border-lab-border bg-lab-elevated p-3 text-sm text-lab-muted"
              >
                <span
                  aria-hidden="true"
                  className="lab-pulse mt-1.5 h-2 w-2 shrink-0 rounded-full bg-lab-warning"
                />
                <span>
                  {wakingNotice}
                  {auth.status === 'unavailable' && !auth.retrying && (
                    <>
                      {' '}
                      <button
                        type="button"
                        onClick={retrySession}
                        className="min-h-8 text-lab-accent underline underline-offset-4"
                      >
                        Retry
                      </button>
                    </>
                  )}
                </span>
              </p>
            )}
          </div>
          <form onSubmit={handleSubmit} className="mt-6 space-y-4" aria-label="Log in">
            <div>
              <label htmlFor="username" className="block text-sm font-medium">
                Username
              </label>
              <input
                id="username"
                name="username"
                autoComplete="username"
                required
                aria-describedby={describedBy}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                aria-invalid={error?.kind === 'credentials' || undefined}
                aria-describedby={describedBy}
                className={inputClass}
              />
            </div>
            {error && (
              <div className="rounded-control border border-lab-danger/50 bg-lab-danger/10 p-3 text-sm">
                <p className="font-mono text-xs tracking-wider text-lab-danger uppercase">
                  {errorTitle[error.kind]}
                </p>
                <p id="login-error" role="alert" className="mt-1 text-lab-text">
                  {error.message}
                </p>
              </div>
            )}
            <button
              type="submit"
              disabled={submitting}
              className="min-h-11 w-full rounded-control bg-lab-accent-strong px-4 font-medium text-white hover:bg-lab-accent-hover disabled:opacity-60"
            >
              {submitting ? 'Logging in…' : 'Log in'}
            </button>
          </form>
        </div>
      </main>
    </div>
  )
}
