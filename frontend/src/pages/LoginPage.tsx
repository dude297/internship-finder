import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/context'
import { ErrorMessage, Field } from '../components/ui'
import { buttonClass, inputClass } from '../lib/styles'

export function LoginPage() {
  const { auth, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

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
      setError(
        caught instanceof ApiError && (caught.status === 401 || caught.status === 429)
          ? caught.message
          : "Couldn't reach the server. Try again.",
      )
      setSubmitting(false)
    }
  }

  return (
    <main className="mx-auto mt-16 max-w-sm p-4 font-sans text-slate-900">
      <h1 className="text-2xl font-semibold">Personal Internship Finder</h1>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4" aria-label="Log in">
        <Field id="username" label="Username">
          <input
            id="username"
            name="username"
            autoComplete="username"
            required
            className={inputClass}
          />
        </Field>
        <Field id="password" label="Password">
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            className={inputClass}
          />
        </Field>
        {error && <ErrorMessage>{error}</ErrorMessage>}
        <button type="submit" disabled={submitting} className={buttonClass}>
          {submitting ? 'Logging in…' : 'Log in'}
        </button>
      </form>
    </main>
  )
}
