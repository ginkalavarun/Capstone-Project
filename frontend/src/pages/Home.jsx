import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { homeFor } from '../lib/roles.js'

/**
 * Landing page: role-aware shortcuts only. Public (D16: browsing needs no
 * login); logged-in users are pointed at their own dashboard.
 */
export default function Home() {
  const { user } = useAuth()
  return (
    <div className="card hero">
      <h1>CampusBite</h1>
      <p>Order food from restaurants around campus, delivered to your door.</p>
      {user ? (
        <Link className="btn btn-primary" to={homeFor(user.role)}>
          Go to your dashboard
        </Link>
      ) : (
        <div className="actions-row">
          <Link className="btn btn-primary" to="/restaurants">
            Browse restaurants
          </Link>
          <Link className="btn" to="/login">
            Log in
          </Link>
        </div>
      )}
    </div>
  )
}
