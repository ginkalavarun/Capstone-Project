import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * Registration (FE-02, D2): creates a CUSTOMER account only. There is
 * deliberately no role field in this form — privileged roles (owner,
 * delivery partner) are provisioned locally by an operator, never by
 * self-service (the backend rejects any `role` field with 422).
 */
export default function Register() {
  const { register } = useAuth()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await register(email.trim(), password, fullName.trim())
      setDone(true)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  if (done) {
    return (
      <div className="card auth-form" role="status">
        <h1>Account created</h1>
        <p>You can now log in with your new account.</p>
        <Link className="btn btn-primary" to="/login">
          Go to log in
        </Link>
      </div>
    )
  }

  return (
    <form className="card form auth-form" onSubmit={submit} aria-busy={busy}>
      <h1>Create an account</h1>
      {error && (
        <div className="notice notice-error" role="alert" id="register-error">
          {error}
        </div>
      )}
      <label htmlFor="reg-name">Full name</label>
      <input
        id="reg-name"
        type="text"
        autoComplete="name"
        required
        minLength={1}
        maxLength={120}
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
      />
      <label htmlFor="reg-email">Email</label>
      <input
        id="reg-email"
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <label htmlFor="reg-password">Password</label>
      <input
        id="reg-password"
        type="password"
        autoComplete="new-password"
        required
        minLength={8}
        maxLength={72}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <p className="muted field-hint">8–72 characters.</p>
      <button type="submit" className="btn btn-primary" disabled={busy || !fullName || !email || !password}>
        {busy ? 'Creating account…' : 'Register'}
      </button>
      <p className="muted">
        Already registered? <Link to="/login">Log in</Link>
      </p>
    </form>
  )
}
