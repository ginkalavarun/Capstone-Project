import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useAuth } from './AuthContext.jsx'

/**
 * Cart state (FE-08, FE-17, D15).
 *
 * Rules:
 *  - one restaurant per cart: adding from another restaurant asks for
 *    confirmation and replaces the cart (the backend enforces the same at
 *    checkout — the frontend check is UX, not security);
 *  - persisted in localStorage, isolated per account: a saved cart that
 *    belongs to a different user is discarded on load, and the cart is
 *    cleared whenever the signed-in account changes;
 *  - quantities are 1–100 (the backend's checkout bounds, T-M6-03);
 *  - totals shown here are ESTIMATES — the server recomputes every total
 *    from the database (D3); the delivery fee is the restaurant's current
 *    fee at browse time and is confirmed at checkout.
 */
const CART_KEY = 'campusbite_cart'
const MAX_QTY = 100

function emptyCart() {
  return { restaurant: null, items: [] }
}

function normalize(saved) {
  if (!saved || !Array.isArray(saved.items)) return emptyCart()
  // The cart's restaurant snapshot may carry the fee under the key the app
  // writes (deliveryFeeCents) or under the API key (delivery_fee_cents) when
  // a stored cart predates a shape change — accept both, default to 0.
  const restaurant = saved.restaurant ?? null
  return {
    restaurant: restaurant
      ? {
          ...restaurant,
          deliveryFeeCents: restaurant.deliveryFeeCents ?? restaurant.delivery_fee_cents ?? 0,
        }
      : null,
    items: saved.items
      .filter((i) => i && i.menuItemId && Number.isFinite(i.priceCents))
      .map((i) => ({
        menuItemId: i.menuItemId,
        name: String(i.name ?? 'Dish'),
        priceCents: Math.trunc(i.priceCents),
        quantity: Math.min(Math.max(1, Math.trunc(i.quantity || 1)), MAX_QTY),
      })),
  }
}

const CartContext = createContext(null)

export function CartProvider({ children }) {
  const { user } = useAuth()
  const userId = user?.id ?? null

  const [cart, setCart] = useState(() => {
    try {
      const saved = normalize(JSON.parse(localStorage.getItem(CART_KEY)))
      // Per-account isolation (FE-17): never inherit another account's cart.
      if (saved.restaurant && saved.restaurant._ownerId !== undefined) {
        return saved.restaurant._ownerId === userId ? saved : emptyCart()
      }
      if (saved.items.length > 0 && userId === null) {
        // Browsing while logged out: keep it, but it dies on the next login.
        return saved
      }
      return saved
    } catch {
      return emptyCart()
    }
  })

  // Clear the cart whenever the signed-in account changes.
  const prevUserId = useRef(userId)
  useEffect(() => {
    if (userId !== prevUserId.current) {
      prevUserId.current = userId
      setCart(emptyCart())
    }
  }, [userId])

  // Persist on change (tagged with the account it belongs to).
  useEffect(() => {
    try {
      localStorage.setItem(
        CART_KEY,
        JSON.stringify({
          restaurant: cart.restaurant
            ? { ...cart.restaurant, _ownerId: userId }
            : null,
          items: cart.items,
        })
      )
    } catch {
      /* storage full/unavailable — the cart stays in memory */
    }
  }, [cart, userId])

  /**
   * Add one dish. Returns true on success, or 'replacement-needed' when the
   * cart holds another restaurant's dishes and {force} is not set.
   */
  const addItem = useCallback(
    (dish, restaurant, { force = false } = {}) => {
      const busy =
        cart.items.length > 0 && cart.restaurant && cart.restaurant.id !== restaurant.id
      if (busy && !force) return 'replacement-needed'
      setCart((c) => {
        const base =
          c.items.length > 0 && c.restaurant && c.restaurant.id === restaurant.id
            ? c
            : { restaurant: { id: restaurant.id, name: restaurant.name, deliveryFeeCents: restaurant.delivery_fee_cents ?? 0 }, items: [] }
        const existing = base.items.find((i) => i.menuItemId === dish.id)
        const items = existing
          ? base.items.map((i) =>
              i.menuItemId === dish.id
                ? { ...i, quantity: Math.min(i.quantity + 1, MAX_QTY) }
                : i
            )
          : [
              ...base.items,
              {
                menuItemId: dish.id,
                name: dish.name,
                priceCents: dish.price_cents,
                quantity: 1,
              },
            ]
        return { ...base, items }
      })
      return true
    },
    [cart.items.length, cart.restaurant]
  )

  const setQuantity = useCallback((menuItemId, quantity) => {
    setCart((c) => {
      if (quantity <= 0) {
        const items = c.items.filter((i) => i.menuItemId !== menuItemId)
        return items.length ? { ...c, items } : emptyCart()
      }
      return {
        ...c,
        items: c.items.map((i) =>
          i.menuItemId === menuItemId ? { ...i, quantity: Math.min(quantity, MAX_QTY) } : i
        ),
      }
    })
  }, [])

  const removeItem = useCallback((menuItemId) => setQuantity(menuItemId, 0), [setQuantity])

  const clear = useCallback(() => setCart(emptyCart()), [])

  const subtotalCents = useMemo(
    () => cart.items.reduce((sum, i) => sum + i.priceCents * i.quantity, 0),
    [cart.items]
  )
  const deliveryFeeCents = cart.restaurant?.deliveryFeeCents ?? null
  const totalCents = subtotalCents + (deliveryFeeCents ?? 0)

  const value = useMemo(
    () => ({
      cart,
      addItem,
      setQuantity,
      removeItem,
      clear,
      subtotalCents,
      deliveryFeeCents,
      totalCents,
      itemCount: cart.items.reduce((n, i) => n + i.quantity, 0),
    }),
    [cart, addItem, setQuantity, removeItem, clear, subtotalCents, deliveryFeeCents, totalCents]
  )

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used inside <CartProvider>')
  return ctx
}
