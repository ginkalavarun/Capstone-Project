import { Link } from 'react-router-dom'

/** 404 page (FE-01/T-M11-01): unknown routes land here. */
export default function NotFound() {
  return (
    <div className="card">
      <h1>404 — page not found</h1>
      <p>That page does not exist.</p>
      <Link className="btn btn-primary" to="/">
        Back to home
      </Link>
    </div>
  )
}
