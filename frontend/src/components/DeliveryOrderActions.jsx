import { useState } from 'react'
import { post } from '../lib/api.js'
import { ConfirmButton } from './ui.jsx'

/**
 * Delivery transitions for one order (FE-12, T-M13-07). Only the ASSIGNED
 * partner may act (the backend returns 404 to anyone else — existence is
 * hidden, AUTHZ-06). Stale/duplicate transitions get 409 and are surfaced.
 *
 *   ASSIGNED         → Out for delivery (POST delivery-status OUT_FOR_DELIVERY)
 *   OUT_FOR_DELIVERY → Delivered        (POST delivery-status DELIVERED)
 */
export function DeliveryOrderActions({ order, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const run = async (target) => {
    setError(null)
    setBusy(true)
    try {
      const updated = await post(`/orders/${order.id}/delivery-status`, { status: target })
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
      {order.status === 'ASSIGNED' && (
        <ConfirmButton
          label="Start delivery"
          confirmLabel="Out for delivery"
          onConfirm={() => run('OUT_FOR_DELIVERY')}
          disabled={busy}
        />
      )}
      {order.status === 'OUT_FOR_DELIVERY' && (
        <ConfirmButton
          label="Mark delivered"
          confirmLabel="Delivered"
          className="btn btn-primary"
          onConfirm={() => run('DELIVERED')}
          disabled={busy}
        />
      )}
    </div>
  )
}
