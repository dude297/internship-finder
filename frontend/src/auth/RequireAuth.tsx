import { Navigate, Outlet, useLocation } from 'react-router'
import { useAuth } from './context'

/** UI convenience only: the API enforces authentication on every private endpoint. */
export function RequireAuth() {
  const { auth } = useAuth()
  const location = useLocation()
  if (auth.status === 'loading') {
    return (
      <p role="status" className="p-8 text-slate-600">
        Loading…
      </p>
    )
  }
  if (auth.status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}
