/**
 * T-M12-01 — cart state: add/update/remove/quantities + persistence.
 * T-M12-12 — per-account isolation: account change clears the previous
 * account's cart; adding from a second restaurant asks to replace (FE-17/D15).
 */
import { describe, expect, it } from 'vitest'
import { act, render, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext.jsx'
import { CartProvider, useCart } from '../CartContext.jsx'
import { tokenStore } from '../../lib/api.js'
import { mockApi } from '../../test/mockApi.js'
import { userCustomer, userOwner, restaurant, restaurantTwo, dish, dishUnavailable } from '../../test/factories.js'

const CART_KEY = 'campusbite_cart'

function renderLiveCart(_user) {
  const cell = { cart: null, auth: null }
  function Probes() {
    cell.auth = useAuth()
    cell.cart = useCart()
    return null
  }
  const view = render(
    <AuthProvider>
      <CartProvider>
        <Probes />
      </CartProvider>
    </AuthProvider>
  )
  cell.unmount = view.unmount
  return cell
}

function seedSession(user, token = 'tok') {
  tokenStore.set(token)
  tokenStore.setUser(user)
}

describe('CartProvider', () => {
  it('add merges duplicate lines, setQuantity clamps, remove clears (T-M12-01)', async () => {
    seedSession(userCustomer)
    mockApi([['GET', '/auth/me', userCustomer]])
    const cell = renderLiveCart()
    await waitFor(() => expect(cell.auth.booting).toBe(false))

    expect(() => {
      act(() => {
        expect(cell.cart.addItem(dish, restaurant)).toBe(true)
        expect(cell.cart.addItem(dish, restaurant)).toBe(true) // same dish again
      })
    }).not.toThrow()
    expect(cell.cart.cart.items).toHaveLength(1)
    expect(cell.cart.cart.items[0].quantity).toBe(2)
    expect(cell.cart.subtotalCents).toBe(2 * dish.price_cents)

    act(() => {
      cell.cart.setQuantity(dish.id, 5)
    })
    expect(cell.cart.cart.items[0].quantity).toBe(5)
    act(() => {
      cell.cart.setQuantity(dish.id, 9999) // clamped to the checkout bound
    })
    expect(cell.cart.cart.items[0].quantity).toBe(100)
    act(() => {
      cell.cart.setQuantity(dish.id, 0) // 0 = remove
    })
    expect(cell.cart.cart.items).toHaveLength(0)
  })

  it('persists to localStorage tagged with the account (T-M12-01 persistence)', async () => {
    seedSession(userCustomer)
    mockApi([['GET', '/auth/me', userCustomer]])
    const cell = renderLiveCart()
    await waitFor(() => expect(cell.auth.booting).toBe(false))

    act(() => {
      cell.cart.addItem(dish, restaurant)
    })
    const stored = JSON.parse(localStorage.getItem(CART_KEY))
    expect(stored.restaurant.id).toBe(restaurant.id)
    expect(stored.restaurant._ownerId).toBe(userCustomer.id)
    expect(stored.items).toHaveLength(1)
  })

  it('a cart saved by a different account is discarded on load (T-M12-12)', async () => {
    // Owner "saves" a cart, then a customer signs in with the same browser.
    seedSession(userOwner)
    mockApi([['GET', '/auth/me', userOwner]])
    const first = renderLiveCart()
    await waitFor(() => expect(first.auth.booting).toBe(false))
    act(() => {
      first.cart.addItem(dish, restaurant)
    })

    // Now the customer logs in (new session, same storage).
    seedSession(userCustomer)
    mockApi([['GET', '/auth/me', userCustomer]])
    const second = renderLiveCart()
    await waitFor(() => expect(second.auth.booting).toBe(false))
    expect(second.cart.cart.items).toHaveLength(0) // not the owner's cart
  })

  it('switching accounts while signed in clears the current cart (T-M12-12)', async () => {
    seedSession(userCustomer)
    mockApi([
      ['GET', '/auth/me', userCustomer],
      [
        'POST',
        '/auth/login',
        { access_token: 'tok-b', token_type: 'bearer', user: userOwner },
      ],
    ])
    const cell = renderLiveCart()
    await waitFor(() => expect(cell.auth.booting).toBe(false))
    act(() => {
      cell.cart.addItem(dish, restaurant)
    })
    expect(cell.cart.cart.items).toHaveLength(1)

    await act(async () => {
      await cell.auth.login('own1@example.org', 'password-123')
    })
    expect(cell.cart.cart.items).toHaveLength(0)
  })

  it('adding from a second restaurant asks to replace, then replaces (T-M12-12, FE-08)', async () => {
    seedSession(userCustomer)
    mockApi([['GET', '/auth/me', userCustomer]])
    const cell = renderLiveCart()
    await waitFor(() => expect(cell.auth.booting).toBe(false))

    act(() => {
      cell.cart.addItem(dish, restaurant) // from Alpha
    })
    const foreignDish = { ...dishUnavailable, restaurant_id: restaurantTwo.id, id: 99 }
    expect(() => {
      act(() => {
        expect(cell.cart.addItem(foreignDish, restaurantTwo)).toBe('replacement-needed')
      })
    }).not.toThrow()
    expect(cell.cart.cart.restaurant.id).toBe(restaurant.id) // unchanged

    act(() => {
      expect(cell.cart.addItem(foreignDish, restaurantTwo, { force: true })).toBe(true)
    })
    expect(cell.cart.cart.restaurant.id).toBe(restaurantTwo.id)
    expect(cell.cart.cart.items).toHaveLength(1)
    expect(cell.cart.cart.items[0].menuItemId).toBe(99)
  })

  it('shows the restaurant fee as an estimate and totals = subtotal + fee', async () => {
    seedSession(userCustomer)
    mockApi([['GET', '/auth/me', userCustomer]])
    const cell = renderLiveCart()
    await waitFor(() => expect(cell.auth.booting).toBe(false))

    act(() => {
      cell.cart.addItem(dish, restaurant) // 1200c
      cell.cart.setQuantity(dish.id, 2)
    })
    expect(cell.cart.subtotalCents).toBe(2400)
    expect(cell.cart.deliveryFeeCents).toBe(250) // Alpha's current fee
    expect(cell.cart.totalCents).toBe(2650)
    expect(cell.cart.itemCount).toBe(2)
  })
})
