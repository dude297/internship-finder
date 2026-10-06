import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router'
import { api } from '../api/client'
import type { DataAge } from '../api/schemas'
import { useAuth } from '../auth/context'
import { ErrorMessage } from './ui'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded px-2 py-1 ${isActive ? 'bg-slate-200 font-medium' : 'hover:bg-slate-100'}`

function age(hours: number): string {
  return hours >= 48 ? `${Math.floor(hours / 24)} days` : `${Math.round(hours)} hours`
}

/** Shown only when the newest successful sync is past the source-health window: the scheduled
 * sync may be paused. Never says postings are closed (ADR-015). Fetch failures show nothing. */
function DataAgeBanner() {
  const [dataAge, setDataAge] = useState<DataAge | null>(null)
  useEffect(() => {
    let active = true
    api
      .getDataAge()
      .then((d) => active && setDataAge(d))
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [])
  if (!dataAge?.stale) return null
  return (
    <aside
      aria-label="Data freshness"
      className="border-b border-amber-300 bg-amber-50 text-amber-900"
    >
      <p className="mx-auto max-w-4xl p-2 text-sm">
        {dataAge.age_hours === null
          ? 'Sources have never synced successfully'
          : `Sources last synced ${age(dataAge.age_hours)} ago`}
        {' — the scheduled sync may be paused. '}
        <Link to="/sources" className="underline">
          Check the Sources page
        </Link>
        .
      </p>
    </aside>
  )
}

export function AppShell() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [logoutFailed, setLogoutFailed] = useState(false)

  async function handleLogout() {
    setLogoutFailed(false)
    try {
      await logout()
    } catch {
      setLogoutFailed(true) // server didn't confirm: the session may still be valid
      return
    }
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen font-sans text-slate-900">
      <header className="border-b border-slate-200">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-4 p-4">
          <p className="text-lg font-semibold">Personal Internship Finder</p>
          <nav aria-label="Main" className="flex gap-2">
            <NavLink to="/dashboard" className={linkClass}>
              Dashboard
            </NavLink>
            <NavLink to="/inbox" className={linkClass}>
              Inbox
            </NavLink>
            <NavLink to="/applications" className={linkClass}>
              Applications
            </NavLink>
            <NavLink to="/profile" className={linkClass}>
              Profile
            </NavLink>
            <NavLink to="/opportunities" className={linkClass}>
              Opportunities
            </NavLink>
            <NavLink to="/sources" className={linkClass}>
              Sources
            </NavLink>
          </nav>
          <button
            type="button"
            onClick={handleLogout}
            className="ml-auto rounded border border-slate-300 px-3 py-1 hover:bg-slate-100"
          >
            Log out
          </button>
        </div>
      </header>
      <DataAgeBanner />
      <main className="mx-auto max-w-4xl p-4">
        {logoutFailed && (
          <div className="mb-4">
            <ErrorMessage>Couldn't log out. You're still signed in.</ErrorMessage>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  )
}
