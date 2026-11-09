import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { homeFor } from '../lib/roles.js'

/**
 * Login (FE-02). Sends only email + password; the token returned by the
 * backend is stored in localStorage (assignment requirement) and every
 * protected request carries it (FE-05).
 */
export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const from = useLocation().state?.from

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  // Already signed in → straight to the role's home (FE-02 redirect-by-role).
  if (user) return <Navigate to={from || homeFor(user.role)} replace />

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const u = await login(email.trim(), password)
      navigate(from || homeFor(u.role), { replace: true })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form className="card form auth-form" onSubmit={submit} aria-busy={busy}>
      <h1>Log in</h1>
      {error && (
        <div className="notice notice-error" role="alert" id="login-error">
          {error}
        </div>
      )}
      <label htmlFor="login-email">Email</label>
      <input
        id="login-email"
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? 'login-error' : undefined}
      />
      <label htmlFor="login-password">Password</label>
      <input
        id="login-password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? 'login-error' : undefined}
      />
      <button type="submit" className="btn btn-primary" disabled={busy || !email || !password}>
        {busy ? 'Logging in…' : 'Log in'}
      </button>
      <p className="muted">
        No account yet? <Link to="/register">Register</Link>
      </p>
    </form>
  )
}
