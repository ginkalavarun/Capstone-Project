import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { post } from '../lib/api.js'
import { useCart } from '../context/CartContext.jsx'
import { newIdempotencyKey } from '../lib/idempotency.js'
import { ApiError } from '../lib/api.js'
import { Money } from '../components/ui.jsx'

/**
 * Checkout (FE-09, CK-01…07, D34).
 *
 * The client sends ONLY: menu item ids, positive quantities, the delivery
 * address, and a client-generated idempotency key. Names, prices, fees,
 * totals, payment status, customer id and order status are never trusted
 * (D3) — the server recomputes everything from the database.
 *
 * Retry semantics (D34): a network failure with the same key + payload
 * returns the ORIGINAL order (200) — the UI treats 201/200 identically
 * ("order #N exists"), so double-clicks and refreshes never create a
 * second order. A 409 IDEMPOTENCY_MISMATCH means the payload changed under
 * a used key: show the error and mint a fresh key for the next attempt.
 */
export default function Checkout() {
  const { cart, clear, subtotalCents, deliveryFeeCents, totalCents } = useCart()

  const [address, setAddress] = useState('')
  const [key, setKey] = useState(() => newIdempotencyKey())
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [placed, setPlaced] = useState(null) // OrderOut on success

  if (placed) {
    return (
      <section className="card" role="status">
        <h1>Order placed</h1>
        <p>
          Thanks! Order <strong>#{placed.id}</strong> for {placed.restaurant_name} was created.
        </p>
        <p>
          Total: <Money cents={placed.total_cents} /> (item subtotal <Money cents={placed.items_subtotal_cents} /> + delivery <Money cents={placed.delivery_fee_cents} />)
        </p>
        <p className="muted">
          The restaurant will accept the order; track its status in “My orders”.
        </p>
        <div className="actions-row">
          <Link className="btn btn-primary" to={`/orders/${placed.id}`}>
            View order
          </Link>
          <Link className="btn" to="/restaurants">
            Order something else
          </Link>
        </div>
      </section>
    )
  }

  if (cart.items.length === 0) return <Navigate to="/cart" replace />

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const order = await post('/orders', {
        items: cart.items.map((i) => ({ menu_item_id: i.menuItemId, quantity: i.quantity })),
        delivery_address: address.trim(),
        idempotency_key: key,
      })
      clear()
      setPlaced(order)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'IDEMPOTENCY_MISMATCH') {
        // Same key, different cart: the key is "used up" — start fresh.
        setKey(newIdempotencyKey())
        setError('The server already processed a different order with this submission id. Adjust your cart and try again.')
      } else {
        setError(err.message)
      }
      setBusy(false)
    }
  }

  return (
    <section className="card" aria-labelledby="checkout-h">
      <h1 id="checkout-h">
        Checkout <span className="muted">— {cart.restaurant?.name}</span>
      </h1>

      <ul className="order-items">
        {cart.items.map((line) => (
          <li key={line.menuItemId}>
            {line.quantity}× {line.name}{' '}
            <span className="muted">
              · <Money cents={line.priceCents * line.quantity} />
            </span>
          </li>
        ))}
      </ul>
      <dl className="order-meta">
        <div>
          <dt>Subtotal</dt>
          <dd>
            <Money cents={subtotalCents} />
          </dd>
        </div>
        <div>
          <dt>Delivery fee</dt>
          <dd>
            <Money cents={deliveryFeeCents ?? 0} />
          </dd>
        </div>
        <div className="cart-total">
          <dt>Total</dt>
          <dd>
            <Money cents={totalCents} />
          </dd>
        </div>
      </dl>

      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}

      <form className="form" onSubmit={submit} aria-busy={busy}>
        <label htmlFor="delivery-address">Delivery address</label>
        <textarea
          id="delivery-address"
          required
          minLength={1}
          maxLength={255}
          rows={3}
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="Dorm, room number, landmark…"
        />
        <p className="muted field-hint">{address.length}/255</p>
        <button type="submit" className="btn btn-primary" disabled={busy || !address.trim()}>
          {busy ? 'Placing order…' : 'Place order'}
        </button>
      </form>
    </section>
  )
}
