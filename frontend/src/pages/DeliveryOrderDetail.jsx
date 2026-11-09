import { Link, useParams } from 'react-router-dom'
import { get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { formatDateTime } from '../lib/format.js'
import { DeliveryOrderActions } from '../components/DeliveryOrderActions.jsx'
import { ErrorNotice, Loading, Money, StatusBadge } from '../components/ui.jsx'

/**
 * Delivery order detail (FE-12, T-M13-07, DELV-02): the full order —
 * customer name + delivery address are shown precisely so the partner can
 * deliver. Anyone who is not the assigned partner gets a 404 from the
 * backend (the partner is never told another order exists).
 */
export default function DeliveryOrderDetail() {
  const { id } = useParams()
  const { data: order, error, loading, reload } = useAsync(
    () => get(`/delivery/orders/${id}`),
    [id]
  )

  if (loading) return <Loading label="Loading delivery…" />
  if (error)
    return (
      <>
        <p>
          <Link to="/delivery">← My deliveries</Link>
        </p>
        <ErrorNotice error={error} onRetry={reload} />
      </>
    )

  return (
    <section className="card" aria-labelledby="dod-h">
      <p>
        <Link to="/delivery">← My deliveries</Link>
      </p>
      <h1 id="dod-h" className="order-head">
        Order #{order.id} · <StatusBadge status={order.status} />
      </h1>

      <dl className="order-meta">
        <div>
          <dt>Customer</dt>
          <dd>{order.customer_name}</dd>
        </div>
        <div>
          <dt>Delivery address</dt>
          <dd>{order.delivery_address}</dd>
        </div>
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
          <dt>Order value</dt>
          <dd>
            <Money cents={order.total_cents} />
          </dd>
        </div>
      </dl>

      <ul className="order-items">
        {order.items.map((line) => (
          <li key={line.id}>
            {line.quantity}× {line.item_name}{' '}
            <span className="muted">· {line.unit_price_cents} cents each</span>
          </li>
        ))}
      </ul>

      <div className="section">
        <DeliveryOrderActions order={order} onChanged={reload} />
      </div>
    </section>
  )
}
