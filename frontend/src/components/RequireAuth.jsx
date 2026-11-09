import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { Loading } from './ui.jsx'

/**
 * Frontend route protection (FE-04) — a UX convenience ONLY.
 *
 * The backend re-checks authentication, role, and resource ownership on
 * every request (D8); hiding a route here grants nothing. Its jobs are:
 *  - no user  → send to /login (remembering where the user was headed);
 *  - wrong role → send to the /forbidden page (never the other role's view,
 *    which would leak what that view contains).
 */
export function RequireAuth({ roles, children }) {
  const { user, booting } = useAuth()
  const location = useLocation()

  if (booting) return <Loading label="Checking your session…" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (roles && !roles.includes(user.role)) return <Navigate to="/forbidden" replace />
  return children
}
