import { Link } from 'react-router-dom'
import { useCart } from '../context/CartContext.jsx'
import { EmptyState, Money } from '../components/ui.jsx'

/**
 * Cart (FE-08). Plain frontend state, persisted per account in localStorage
 * (FE-17). The delivery fee shown is the restaurant's current fee — an
 * estimate; the server recomputes all totals at checkout (D3).
 */
export default function Cart() {
  const { cart, setQuantity, removeItem, clear, subtotalCents, deliveryFeeCents, totalCents } =
    useCart()

  if (cart.items.length === 0) {
    return (
      <section aria-labelledby="cart-h">
        <h1 id="cart-h">Your cart</h1>
        <EmptyState
          title="Your cart is empty."
          hint="Browse a restaurant's menu and add dishes."
          action={
            <Link className="btn btn-primary" to="/restaurants">
              Browse restaurants
            </Link>
          }
        />
      </section>
    )
  }

  return (
    <section className="card" aria-labelledby="cart-h">
      <h1 id="cart-h">
        Your cart <span className="muted">— {cart.restaurant?.name}</span>
      </h1>

      <table className="cart-table">
        <thead>
          <tr>
            <th scope="col">Dish</th>
            <th scope="col">Unit price</th>
            <th scope="col">Quantity</th>
            <th scope="col">Line total</th>
            <th scope="col">
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {cart.items.map((line) => (
            <tr key={line.menuItemId}>
              <td>{line.name}</td>
              <td>
                <Money cents={line.priceCents} />
              </td>
              <td>
                <span className="qty-stepper">
                  <button
                    type="button"
                    aria-label={`Decrease quantity of ${line.name}`}
                    onClick={() => setQuantity(line.menuItemId, line.quantity - 1)}
                  >
                    −
                  </button>
                  <span aria-live="polite">{line.quantity}</span>
                  <button
                    type="button"
                    aria-label={`Increase quantity of ${line.name}`}
                    disabled={line.quantity >= 100}
                    onClick={() => setQuantity(line.menuItemId, line.quantity + 1)}
                  >
                    +
                  </button>
                </span>
              </td>
              <td>
                <Money cents={line.priceCents * line.quantity} />
              </td>
              <td>
                <button
                  type="button"
                  className="btn btn-danger"
                  aria-label={`Remove ${line.name} from cart`}
                  onClick={() => removeItem(line.menuItemId)}
                >
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={2}>Subtotal</td>
            <td />
            <td>
              <Money cents={subtotalCents} />
            </td>
            <td />
          </tr>
          <tr>
            <td colSpan={2}>Delivery fee (estimated)</td>
            <td />
            <td>
              <Money cents={deliveryFeeCents ?? 0} />
            </td>
            <td />
          </tr>
          <tr className="cart-total">
            <td colSpan={3}>Total (estimated)</td>
            <td>
              <Money cents={totalCents} />
            </td>
            <td />
          </tr>
        </tfoot>
      </table>

      <p className="muted">
        Final prices are confirmed by the restaurant's current menu and fee when your order is
        placed.
      </p>

      <div className="actions-row">
        <button type="button" className="btn btn-danger" onClick={clear}>
          Clear cart
        </button>
        <Link className="btn btn-primary" to="/checkout">
          Proceed to checkout
        </Link>
      </div>
    </section>
  )
}
