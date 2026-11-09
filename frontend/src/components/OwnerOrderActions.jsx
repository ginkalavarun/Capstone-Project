import { useState } from 'react'
import { post, get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { ConfirmButton } from './ui.jsx'

/**
 * Owner transition buttons for one order (FE-11, T-M13-02).
 *
 * Buttons appear ONLY per the order's current status — the central state
 * machine in the backend (D7) is the real rule; a stale/duplicate click
 * gets a 409 INVALID_TRANSITION, which is surfaced, not swallowed.
 *
 *   PLACED  → Accept            (POST /orders/{id}/accept)
 *   ACCEPTED→ Start preparing   (POST /orders/{id}/status PREPARING)
 *   PREPARING → Mark ready      (POST /orders/{id}/status READY)
 *   READY   → Assign partner    (POST /orders/{id}/assign, from the
 *                                protected active-partner listing, DELV-04)
 */
export function OwnerOrderActions({ order, onChanged }) {
  const partners = useAsync(() => get('/delivery-partners'), [])
  const [selectedPartner, setSelectedPartner] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const run = async (fn) => {
    setError(null)
    setBusy(true)
    try {
      const updated = await fn()
      if (onChanged) await onChanged(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="order-actions">
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}

      {order.status === 'PLACED' && (
        <ConfirmButton label="Accept" confirmLabel="Accept order" onConfirm={() => run(() => post(`/orders/${order.id}/accept`))} disabled={busy} />
      )}
      {order.status === 'ACCEPTED' && (
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => run(() => post(`/orders/${order.id}/status`, { status: 'PREPARING' }))}
        >
          Start preparing
        </button>
      )}
      {order.status === 'PREPARING' && (
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => run(() => post(`/orders/${order.id}/status`, { status: 'READY' }))}
        >
          Mark ready
        </button>
      )}
      {order.status === 'READY' && (
        <span className="assign-row">
          <label htmlFor={`assign-${order.id}`}>Assign to</label>
          <select
            id={`assign-${order.id}`}
            value={selectedPartner}
            disabled={busy || partners.loading}
            onChange={(e) => setSelectedPartner(e.target.value)}
          >
            <option value="">Select a delivery partner…</option>
            {partners.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name}
              </option>
            ))}
          </select>
          <ConfirmButton
            label="Assign"
            confirmLabel="Confirm assignment"
            disabled={!selectedPartner || busy}
            onConfirm={() =>
              run(() => post(`/orders/${order.id}/assign`, { delivery_partner_id: Number(selectedPartner) }))
            }
          />
        </span>
      )}
    </div>
  )
}
