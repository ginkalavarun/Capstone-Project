import { Component } from 'react'

/**
 * Last-resort error boundary (FE-14): render errors in an async view are
 * handled by useAsync; this catches the unexpected rest so the whole app
 * never white-screens.
 */
export class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Never log user data or tokens (D23) — component stack only.
    console.error('ErrorBoundary caught a render error:', info?.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" className="notice notice-error app-error">
        <h1>Something went wrong</h1>
        <p>The page could not be rendered. Reloading usually fixes it.</p>
        <button type="button" className="btn" onClick={() => window.location.reload()}>
          Reload the app
        </button>
      </div>
    )
  }
}
