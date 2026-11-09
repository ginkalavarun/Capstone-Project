import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { get, post } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { formatDateTime } from '../lib/format.js'
import { OwnerOrderActions } from '../components/OwnerOrderActions.jsx'
import { ConfirmButton, ErrorNotice, Loading, Money, StatusBadge } from '../components/ui.jsx'

/**
 * Owner view of one order (FE-11, T-M13-02/03): lifecycle actions plus the
 * refund decision.
 *
 * Refund rules (D28/D30): the request is decided with a single atomic
 * transaction on the backend — approve marks the order REFUNDED, the
 * payment refunded, and writes exactly one `refunded` ledger row. Deciding
 * twice returns 409 REFUND_ALREADY_DECIDED (a double-approve is a 200
 * no-op). Rejecting leaves the order DELIVERED / mock_paid untouched.
 */
export default function OwnerOrderDetail() {
  const { id } = useParams()
  const { data: order, error, loading, reload } = useAsync(() => get(`/orders/${id}`), [id])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const [actionError, setActionError] = useState(null)

  if (loading) return <Loading label="Loading order…" />
  if (error)
    return (
      <>
        <p>
          <Link to="/owner/orders">← Orders</Link>
        </p>
        <ErrorNotice error={error} onRetry={reload} />
      </>
    )

  const decide = async (decision) => {
    setActionError(null)
    setNotice(null)
    setBusy(true)
    try {
      await post(`/orders/${id}/refund/${decision}`)
      setNotice(
        decision === 'approve'
          ? 'Refund approved — the order is now REFUNDED and the mock payment fully reversed.'
          : 'Refund request rejected — the order stays delivered/paid.'
      )
      reload()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card" aria-labelledby="oo-h">
      <p>
        <Link to="/owner/orders">← Orders</Link>
      </p>
      <h1 id="oo-h" className="order-head">
        <span className="muted">Order #{order.id} · {order.customer_name}</span>{' '}
        <StatusBadge status={order.status} />
      </h1>

      <ul className="order-items">
        {order.items.map((line) => (
          <li key={line.id}>
            {line.quantity}× {line.item_name} <span className="muted">· {line.unit_price_cents} cents each</span>
          </li>
        ))}
      </ul>

      <dl className="order-meta">
        <div>
          <dt>Placed</dt>
          <dd>{formatDateTime(order.created_at)}</dd>
        </div>
        <div>
          <dt>Status since</dt>
          <dd>{formatDateTime(order.status_updated_at)}</dd>
        </div>
        {order.delivered_at && (
          <div>
            <dt>Delivered</dt>
            <dd>{formatDateTime(order.delivered_at)}</dd>
          </div>
        )}
        <div className="cart-total">
          <dt>Total</dt>
          <dd>
            <Money cents={order.total_cents} />
          </dd>
        </div>
        <div>
          <dt>Payment</dt>
          <dd>{order.payment_status.replace(/_/g, ' ')}</dd>
        </div>
        <div>
          <dt>Deliver to</dt>
          <dd>{order.delivery_address}</dd>
        </div>
      </dl>

      {notice && (
        <div className="notice notice-info" role="status">
          {notice}
        </div>
      )}
      {actionError && (
        <div className="notice notice-error" role="alert">
          {actionError}
        </div>
      )}

      <div className="section">
        <OwnerOrderActions order={order} onChanged={reload} />
      </div>

      {order.refund_status && (
        <div className="section">
          <h2>
            Refund request <span className="muted">({order.refund_status})</span>
          </h2>
          {order.refund_status === 'pending' && (
            <>
              <p>
                Customer reason: <em>{order.refund_reason || '—'}</em>
              </p>
              <div className="actions-row">
                <ConfirmButton
                  label="Approve refund"
                  confirmLabel="Approve + refund"
                  className="btn"
                  onConfirm={() => decide('approve')}
                  disabled={busy}
                />
                <ConfirmButton
                  label="Reject"
                  confirmLabel="Reject refund"
                  className="btn btn-danger"
                  onConfirm={() => decide('reject')}
                  disabled={busy}
                />
              </div>
            </>
          )}
          {order.refund_status === 'approved' && <p>Refund paid out — one ledger reversal recorded.</p>}
          {order.refund_status === 'rejected' && (
            <p>Refund rejected — the customer cannot request again (one per order).</p>
          )}
        </div>
      )}
    </section>
  )
}
