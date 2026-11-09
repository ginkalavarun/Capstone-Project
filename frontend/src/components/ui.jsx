import { useState } from 'react'
import { money } from '../lib/format.js'

/** Async views show this while loading (FE-14). */
export function Loading({ label = 'Loading…' }) {
  return (
    <p role="status" className="loading">
      {label}
    </p>
  )
}

/** role=alert so screen readers announce failures (FE-14, FE-16). */
export function ErrorNotice({ error, onRetry }) {
  return (
    <div role="alert" className="notice notice-error">
      <p>{error?.message || 'Something went wrong.'}</p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, hint, action }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {hint && <p className="empty-hint">{hint}</p>}
      {action}
    </div>
  )
}

/** Integer cents → "€12.34" (D3/D26: display-only, no float math). */
export function Money({ cents, className = '' }) {
  return <span className={`money ${className}`.trim()}>{money(cents)}</span>
}

const BADGE_CLASS = {
  PLACED: 'badge-placed',
  ACCEPTED: 'badge-accepted',
  PREPARING: 'badge-preparing',
  READY: 'badge-ready',
  ASSIGNED: 'badge-assigned',
  OUT_FOR_DELIVERY: 'badge-ofd',
  DELIVERED: 'badge-delivered',
  CANCELLED: 'badge-cancelled',
  REFUNDED: 'badge-refunded',
}

export function StatusBadge({ status }) {
  return <span className={`badge ${BADGE_CLASS[status] || ''}`}>{status.replace(/_/g, ' ')}</span>
}

/** Previous/next pagination over the standard `Page` envelope (contract §1). */
export function Pagination({ page, total, onPage, baseLabel = 'Showing' }) {
  if (!total) return null
  const from = page.offset + 1
  const to = Math.min(page.offset + page.limit, total)
  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        className="btn"
        disabled={page.offset === 0}
        onClick={() => onPage({ ...page, offset: Math.max(0, page.offset - page.limit) })}
      >
        ← Previous
      </button>
      <span aria-live="polite">
        {baseLabel} {from}–{to} of {total}
      </span>
      <button
        type="button"
        className="btn"
        disabled={to >= total}
        onClick={() => onPage({ ...page, offset: page.offset + page.limit })}
      >
        Next →
      </button>
    </nav>
  )
}

/**
 * Two-step destructive action (avoids window.confirm, which is not
 * keyboard/AT friendly): the button asks for confirmation before acting.
 */
export function ConfirmButton({ label, confirmLabel = 'Confirm', onConfirm, disabled, className = 'btn' }) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)

  const act = async () => {
    setBusy(true)
    try {
      await onConfirm()
    } finally {
      setBusy(false)
      setArmed(false)
    }
  }

  if (armed) {
    return (
      <span className="confirm-pair">
        <button
          type="button"
          className={`${className} btn-danger`}
          disabled={busy}
          aria-label={confirmLabel}
          onClick={act}
        >
          {busy ? 'Working…' : confirmLabel}
        </button>
        <button
          type="button"
          className="btn"
          disabled={busy}
          aria-label="Cancel"
          onClick={() => setArmed(false)}
        >
          Cancel
        </button>
      </span>
    )
  }
  return (
    <button type="button" className={className} disabled={disabled || busy} onClick={() => setArmed(true)}>
      {label}
    </button>
  )
}
