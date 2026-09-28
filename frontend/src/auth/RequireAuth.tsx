import { Navigate, Outlet, useLocation } from 'react-router'
import { secondaryButtonClass } from '../lib/styles'
import { useAuth } from './context'

/** UI convenience only: the API enforces authentication on every private endpoint. */
export function RequireAuth() {
  const { auth, retrySession } = useAuth()
  const location = useLocation()
  if (auth.status === 'loading') {
    return (
      <p role="status" className="p-8 text-slate-600">
        Loading…
      </p>
    )
  }
  if (auth.status === 'unavailable') {
    // Not logged out: the backend (e.g. Render waking from sleep) just hasn't answered yet.
    return (
      <div className="space-y-3 p-8 text-slate-600">
        <p role="status">
          {auth.retrying
            ? 'Server is waking up… This can take up to a minute.'
            : "Can't reach the server right now."}
        </p>
        <button type="button" onClick={retrySession} className={secondaryButtonClass}>
          Retry
        </button>
      </div>
    )
  }
  if (auth.status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}
