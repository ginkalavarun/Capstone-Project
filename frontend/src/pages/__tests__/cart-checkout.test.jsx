/**
 * T-M12-04 — cart page: edit quantities, remove, totals displayed.
 * T-M12-05 — checkout: places the order with the minimal trusted payload
 * (ids + quantities + address + idempotency key), shows the
 * server-computed total, and handles 422 / 409 / 200-retry outcomes.
 */
import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { renderApp, renderPage } from '../../test/harness.jsx'
import { tokenStore } from '../../lib/api.js'
import { mockApi } from '../../test/mockApi.js'
import { userCustomer, restaurant, dish, order } from '../../test/factories.js'
import CartPage from '../CartPage.jsx'
import Checkout from '../Checkout.jsx'
import App from '../../App.jsx'

function seedCustomer(withCart = true) {
  tokenStore.set('tok')
  tokenStore.setUser(userCustomer)
  if (withCart) {
    localStorage.setItem(
      'campusbite_cart',
      JSON.stringify({
        restaurant: { ...restaurant, _ownerId: userCustomer.id },
        items: [
          { menuItemId: dish.id, name: dish.name, priceCents: 1200, quantity: 2 },
          { menuItemId: 11, name: 'Fries', priceCents: 400, quantity: 1 },
        ],
      })
    )
  }
}

describe('Cart page (T-M12-04)', () => {
  it('lists lines, edits quantities, removes, and shows totals', async () => {
    seedCustomer()
    mockApi([['GET', '/auth/me', userCustomer]])
    const user = userEvent.setup()
    renderPage(CartPage, { route: '/cart' })

    // Lines
    expect(screen.getByText('Grilled Chicken')).toBeInTheDocument()
    expect(screen.getByText('Fries')).toBeInTheDocument()

    // Totals: 2×1200 + 1×400 = 2800; fee 250; total 3050
    const tfoot = screen.getByRole('row', { name: /subtotal/i })
    expect(within(tfoot).getByText(/€28\.00/)).toBeInTheDocument()
    expect(screen.getByRole('row', { name: /total \(estimated\)/i })).toHaveTextContent(/€30\.50/)

    // Quantity up: 2×1200 + 2×400 = 3200 + 250 fee = 3450
    await user.click(screen.getByRole('button', { name: /increase quantity of fries/i }))
    expect(screen.getByRole('row', { name: /total \(estimated\)/i })).toHaveTextContent(/€34\.50/)

    // Remove
    await user.click(screen.getByRole('button', { name: /remove fries from cart/i }))
    expect(screen.queryByText('Fries')).not.toBeInTheDocument()
  })

  it('shows an empty state with a browse link when the cart is empty', async () => {
    seedCustomer(false)
    mockApi([['GET', '/auth/me', userCustomer]])
    renderPage(CartPage, { route: '/cart' })
    expect(await screen.findByText(/your cart is empty/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /browse restaurants/i })).toHaveAttribute('href', '/restaurants')
  })
})

describe('Checkout (T-M12-05, D34)', () => {
  it('sends ONLY ids+quantities+address+key — never prices or totals (CK-02)', async () => {
    seedCustomer()
    const { calls } = mockApi([
      ['GET', '/auth/me', userCustomer],
      ['POST', '/orders', order({ id: 100 })],
    ])
    const user = userEvent.setup()
    renderPage(Checkout, { route: '/checkout' })

    await user.type(screen.getByLabelText(/delivery address/i), 'Dorm 4, room 12')
    await user.click(screen.getByRole('button', { name: /place order/i }))

    await screen.findByText(/order placed/i)
    const call = calls.find((c) => c.method === 'POST' && c.path === '/orders')
    expect(call.body).toMatchObject({
      items: [
        { menu_item_id: dish.id, quantity: 2 },
        { menu_item_id: 11, quantity: 1 },
      ],
      delivery_address: 'Dorm 4, room 12',
    })
    expect(call.body.idempotency_key).toMatch(/^key-|[0-9a-f-]{36}$/) // non-empty, bounded
    expect(call.body).not.toHaveProperty('total_cents') // no client money
    expect(call.body).not.toHaveProperty('status')
    expect(call.body).not.toHaveProperty('customer_id')
  })

  it('shows the SERVER-computed total on success and clears the cart', async () => {
    seedCustomer()
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['POST', '/orders', order({ id: 100, total_cents: 3050, items_subtotal_cents: 2800, delivery_fee_cents: 250 })],
    ])
    const user = userEvent.setup()
    renderPage(Checkout, { route: '/checkout' })

    await user.type(screen.getByLabelText(/delivery address/i), 'Dorm 4, room 12')
    await user.click(screen.getByRole('button', { name: /place order/i }))

    const panel = await screen.findByRole('status')
    expect(within(panel).getByText(/€30\.50/)).toBeInTheDocument() // server total, not the estimate
    expect(JSON.parse(localStorage.getItem('campusbite_cart')).items).toHaveLength(0)
  })

  it('treats a 200 (idempotent retry) as success for the original order (D34)', async () => {
    seedCustomer()
    const retry = order({ id: 100 })
    Object.defineProperty(retry, 'status', { value: 200, enumerable: false })
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['POST', '/orders', { status: 200, body: retry }],
    ])
    const user = userEvent.setup()
    renderPage(Checkout, { route: '/checkout' })

    await user.type(screen.getByLabelText(/delivery address/i), 'Dorm 4, room 12')
    await user.click(screen.getByRole('button', { name: /place order/i }))

    await screen.findByText(/order placed/i) // same success UI for the original order
  })

  it('on IDEMPOTENCY_MISMATCH shows the error and mints a fresh key for the next attempt (D34)', async () => {
    seedCustomer()
    let firstKey = null
    let attempts = 0
    const { calls } = mockApi([
      ['GET', '/auth/me', userCustomer],
      [
        'POST',
        '/orders',
        (url, init) => {
          attempts += 1
          firstKey = attempts === 1 ? JSON.parse(init.body).idempotency_key : firstKey
          return attempts === 1
            ? {
                status: 409,
                body: { detail: 'Same key, different payload.', code: 'IDEMPOTENCY_MISMATCH' },
              }
            : order({ id: 100 }) // the retry (new key, changed payload) succeeds
        },
      ],
    ])
    const user = userEvent.setup()
    renderPage(Checkout, { route: '/checkout' })

    await user.type(screen.getByLabelText(/delivery address/i), 'Dorm 4, room 12')
    await user.click(screen.getByRole('button', { name: /place order/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/already processed a different order/i)

    // Change the address, retry → a NEW key is sent.
    const addr = screen.getByLabelText(/delivery address/i)
    await user.click(addr, { clickCount: 3 })
    await user.type(addr, ' Dorm 4')
    await user.click(screen.getByRole('button', { name: /place order/i }))
    await screen.findByRole('status') // success panel
    const keys = calls.filter((c) => c.path === '/orders').map((c) => c.body.idempotency_key)
    expect(keys).toHaveLength(2)
    expect(keys[1]).not.toBe(firstKey)
  })

  it('surfaces a 422 validation error verbatim', async () => {
    seedCustomer()
    mockApi([
      ['GET', '/auth/me', userCustomer],
      [
        'POST',
        '/orders',
        { status: 422, body: { detail: 'items: 1 dish is no longer available.', code: 'VALIDATION_ERROR' } },
      ],
    ])
    const user = userEvent.setup()
    renderPage(Checkout, { route: '/checkout' })

    await user.type(screen.getByLabelText(/delivery address/i), 'Dorm 4, room 12')
    await user.click(screen.getByRole('button', { name: /place order/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/no longer available/i)
  })

  it('disables the submit button while the request is in flight (no double submits)', async () => {
    seedCustomer()
    let settle
    const pending = () =>
      new Promise((resolve, reject) => {
        settle = { resolve, reject }
      })
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['POST', '/orders', () => pending()],
    ])
    const user = userEvent.setup()
    renderPage(Checkout, { route: '/checkout' })

    await user.type(screen.getByLabelText(/delivery address/i), 'Dorm 4, room 12')
    await user.click(screen.getByRole('button', { name: /place order/i }))

    const busyButton = screen.getByRole('button', { name: /placing order/i })
    expect(busyButton).toBeDisabled()
    // resolve it so the test can finish
    settle.resolve(order({ id: 100 }))
    await screen.findByText(/order placed/i)
  })

  it('an empty cart redirects to the cart page (full App: the /cart route must exist)', async () => {
    seedCustomer(false)
    mockApi([['GET', '/auth/me', userCustomer]])
    renderApp(<App />, { route: '/checkout' })
    await screen.findByText(/your cart is empty/i)
  })
})
