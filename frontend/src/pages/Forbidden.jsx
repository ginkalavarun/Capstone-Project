import { Link } from 'react-router-dom'

/** 403 page (FE-04): a valid login whose role does not match the route. */
export default function Forbidden() {
  return (
    <div className="card" role="alert">
      <h1>403 — not allowed</h1>
      <p>Your account does not have access to that page.</p>
      <Link className="btn btn-primary" to="/">
        Back to home
      </Link>
    </div>
  )
}
