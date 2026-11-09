import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { get, post } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { DELIVERY_FLOW } from '../lib/roles.js'
import { formatDateTime } from '../lib/format.js'
import { ConfirmButton, ErrorNotice, Loading, Money, StatusBadge } from '../components/ui.jsx'

/**
 * Customer order detail (FE-10: ORDR-02 + cancellation + refund + review).
 *
 * Action eligibility is driven by the SERVER state in the response, never
 * by local assumptions (FE: "use current server state to determine
 * available actions"):
 *   - cancel:        only while status is PLACED (D29);
 *   - refund request: only DELIVERED while no request exists yet (D28);
 *   - review:        once delivered_at is set (D31 — a later refund keeps
 *                    eligibility); one review per order (REV-02).
 */
export default function CustomerOrderDetail() {
  const { id } = useParams()
  const { data: order, error, loading, reload } = useAsync(() => get(`/orders/${id}`), [id])

  const [notice, setNotice] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [reason, setReason] = useState('')
  const [rating, setRating] = useState('5')
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)

  if (loading) return <Loading label="Loading order…" />
  if (error)
    return (
      <>
        <p>
          <Link to="/orders">← My orders</Link>
        </p>
        <ErrorNotice error={error} onRetry={reload} />
      </>
    )

  const run = async (fn, okMsg) => {
    setActionError(null)
    setNotice(null)
    setBusy(true)
    try {
      await fn()
      setNotice(okMsg)
      reload()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const cancel = () =>
    run(() => post(`/orders/${id}/cancel`), 'Order cancelled — the mock payment was reversed.')
  const requestRefund = () =>
    run(
      () => post(`/orders/${id}/refund-request`, { reason: reason.trim() }),
      'Refund request sent — the restaurant owner will decide.'
    )
  const submitReview = () =>
    run(
      () => post(`/orders/${id}/review`, { rating: Number(rating), comment: comment.trim() || null }),
      'Thanks for your review!'
    )

  const statusIndex = DELIVERY_FLOW.indexOf(order.status)

  return (
    <section className="card" aria-labelledby="order-h">
      <p>
        <Link to="/orders">← My orders</Link>
      </p>
      <h1 id="order-h" className="order-head">
        {order.restaurant_name} <span className="muted">· order #{order.id}</span>{' '}
        <StatusBadge status={order.status} />
      </h1>

      {order.status === 'CANCELLED' || order.status === 'REFUNDED' ? (
        <p className="muted">
          This order ended as {order.status.replace(/_/g, ' ')}
          {order.status === 'CANCELLED'
            ? ' — the mock payment was fully reversed.'
            : ' — the refund was approved and the mock payment was reversed.'}
        </p>
      ) : (
        <ol className="timeline" aria-label="Order progress">
          {DELIVERY_FLOW.map((s, i) => (
            <li key={s} className={s === order.status ? 'current' : i < statusIndex ? 'done' : ''}>
              {s.replace(/_/g, ' ')}
            </li>
          ))}
        </ol>
      )}

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
          <dt>Item subtotal</dt>
          <dd>
            <Money cents={order.items_subtotal_cents} />
          </dd>
        </div>
        <div>
          <dt>Delivery fee</dt>
          <dd>
            <Money cents={order.delivery_fee_cents} />
          </dd>
        </div>
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
        {order.delivered_at && (
          <div>
            <dt>Delivered</dt>
            <dd>{formatDateTime(order.delivered_at)}</dd>
          </div>
        )}
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

      {/* Cancel — customer, PLACED only (D29). */}
      {order.status === 'PLACED' && (
        <div className="actions-row">
          <ConfirmButton
            label="Cancel order"
            confirmLabel="Yes, cancel"
            onConfirm={cancel}
            disabled={busy}
          />
        </div>
      )}

      {/* Refund request — DELIVERED only, one per order permanently (D28). */}
      {(order.status === 'DELIVERED' || order.status === 'REFUNDED') && (
        <div className="section">
          <h2>Refund</h2>
          {order.refund_status === 'approved' && (
            <p role="status">
              Your refund was approved — the full total (including the delivery fee) was reversed.
            </p>
          )}
          {order.refund_status === 'pending' && (
            <p role="status">
              Your refund request is pending — the restaurant owner will approve or reject it.
            </p>
          )}
          {order.refund_status === 'rejected' && (
            <p role="status">
              The restaurant rejected your refund request. One request per order — no further
              requests are possible.
            </p>
          )}
          {!order.refund_status && order.status === 'DELIVERED' && (
            <form
              className="form"
              onSubmit={(e) => {
                e.preventDefault()
                requestRefund()
              }}
            >
              <label htmlFor="refund-reason">Why do you want a refund?</label>
              <textarea
                id="refund-reason"
                required
                minLength={1}
                maxLength={1000}
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <button type="submit" className="btn btn-danger" disabled={busy || !reason.trim()}>
                Request refund
              </button>
            </form>
          )}
        </div>
      )}

      {/* Review — once delivered (D31), one per order (REV-02). */}
      {order.delivered_at && (
        <div className="section">
          <h2>Review</h2>
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault()
              submitReview()
            }}
          >
            <label htmlFor="review-rating">Rating</label>
            <select id="review-rating" value={rating} onChange={(e) => setRating(e.target.value)}>
              {[5, 4, 3, 2, 1].map((n) => (
                <option key={n} value={n}>
                  {n} star{n > 1 ? 's' : ''}
                </option>
              ))}
            </select>
            <label htmlFor="review-comment">Comment (optional)</label>
            <textarea
              id="review-comment"
              maxLength={1000}
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
            <button type="submit" className="btn" disabled={busy}>
              Submit review
            </button>
          </form>
        </div>
      )}
    </section>
  )
}
