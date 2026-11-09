import { Link } from 'react-router-dom'
import { formatDateTime, money } from '../lib/format.js'
import { Money, StatusBadge } from './ui.jsx'

/**
 * One order row, shared by the customer, owner, and delivery views.
 * `detailTo` is role-specific (each role is authorized for a different
 * detail endpoint by the backend — the card only renders the link it is
 * given, it does not "know" about authorization).
 */
export function OrderCard({ order, detailTo, actions }) {
  return (
    <article className="card order-card">
      <header className="order-head">
        <Link to={detailTo} className="order-title">
          {order.restaurant_name} <span className="muted">· order #{order.id}</span>
        </Link>
        <StatusBadge status={order.status} />
      </header>

      <ul className="order-items" aria-label="Items">
        {order.items.map((line) => (
          <li key={line.id}>
            {line.quantity}× {line.item_name} <span className="muted">· {money(line.unit_price_cents)} each</span>
          </li>
        ))}
      </ul>

      <dl className="order-meta">
        <div>
          <dt>Placed</dt>
          <dd>{formatDateTime(order.created_at)}</dd>
        </div>
        <div>
          <dt>Total</dt>
          <dd>
            <Money cents={order.total_cents} />
          </dd>
        </div>
        {order.customer_name && (
          <div>
            <dt>Customer</dt>
            <dd>{order.customer_name}</dd>
          </div>
        )}
        {order.delivery_address && (
          <div>
            <dt>Deliver to</dt>
            <dd>{order.delivery_address}</dd>
          </div>
        )}
        {order.refund_status && (
          <div>
            <dt>Refund</dt>
            <dd className="refund-chip">{order.refund_status}</dd>
          </div>
        )}
      </dl>

      {actions}
    </article>
  )
}
