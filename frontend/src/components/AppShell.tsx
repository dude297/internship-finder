import { NavLink, Outlet, useNavigate } from 'react-router'
import { useAuth } from '../auth/context'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded px-2 py-1 ${isActive ? 'bg-slate-200 font-medium' : 'hover:bg-slate-100'}`

export function AppShell() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout().catch(() => undefined)
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen font-sans text-slate-900">
      <header className="border-b border-slate-200">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-4 p-4">
          <p className="text-lg font-semibold">Personal Internship Finder</p>
          <nav aria-label="Main" className="flex gap-2">
            <NavLink to="/profile" className={linkClass}>
              Profile
            </NavLink>
            <NavLink to="/opportunities" className={linkClass}>
              Opportunities
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
      <main className="mx-auto max-w-4xl p-4">
        <Outlet />
      </main>
    </div>
  )
}
