/**
 * T-M12-03 — menu page: dishes, prices formatted from cents, add-to-cart,
 * unavailable dishes excluded, server-side filters sent as query params.
 */
import { describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { renderPage } from '../../test/harness.jsx'
import { tokenStore } from '../../lib/api.js'
import { mockApi } from '../../test/mockApi.js'
import { userCustomer, restaurant, dish, dishUnavailable } from '../../test/factories.js'
import Menu from '../Menu.jsx'

function seedCustomer() {
  tokenStore.set('tok')
  tokenStore.setUser(userCustomer)
}

describe('Menu page', () => {
  it('renders dishes with EUR prices and adds to cart (T-M12-03)', async () => {
    seedCustomer()
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['GET', '/restaurants/1', restaurant],
      ['GET', '/restaurants/1/menu', { items: [dish, dishUnavailable], total: 2, limit: 20, offset: 0 }],
    ])
    const user = userEvent.setup()
    renderPage(Menu, { route: '/restaurants/1', pattern: '/restaurants/:id' })

    await screen.findByText('Grilled Chicken')
    expect(screen.getByText(/€12/)).toBeInTheDocument() // 1200 cents
    expect(screen.getByText(/€4/)).toBeInTheDocument() // 400 cents

    const addButtons = screen.getAllByRole('button', { name: /add to cart/i })
    expect(addButtons).toHaveLength(1) // only the AVAILABLE dish offers a button
    await user.click(addButtons[0])
    expect(await screen.findByText(/added grilled chicken/i)).toBeInTheDocument()
  })

  it('marks soft-removed dishes as not available (no add button; MENU-07)', async () => {
    seedCustomer()
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['GET', '/restaurants/1', restaurant],
      ['GET', '/restaurants/1/menu', { items: [dishUnavailable], total: 1, limit: 20, offset: 0 }],
    ])
    renderPage(Menu, { route: '/restaurants/1', pattern: '/restaurants/:id' })

    await screen.findByText('Fries')
    expect(screen.getByText(/not available/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add to cart/i })).not.toBeInTheDocument()
  })

  it('sends price filters as integer cents (euros in, cents to the API)', async () => {
    seedCustomer()
    const { calls } = mockApi([
      ['GET', '/auth/me', userCustomer],
      ['GET', '/restaurants/1', restaurant],
      ['GET', '/restaurants/1/menu', { items: [dish], total: 1, limit: 20, offset: 0 }],
    ])
    const user = userEvent.setup()
    renderPage(Menu, { route: '/restaurants/1', pattern: '/restaurants/:id' })
    await screen.findByText('Grilled Chicken')

    await user.type(screen.getByLabelText(/min €|min/i), '5')
    await user.type(screen.getByLabelText(/max €|max/i), '20')
    await user.type(screen.getByLabelText(/dish/i), 'grill')
    await user.click(screen.getByRole('button', { name: /filter/i }))

    // Wait for the filtered request (the first menu call had no params):
    // the refetch happens after React processes the submitted state.
    await vi.waitFor(() => {
      const menuCalls = calls.filter((c) => c.path.endsWith('/menu'))
      const filtered = menuCalls.at(-1)
      expect(filtered.query.get('min_price_cents')).toBe('500')
      expect(filtered.query.get('max_price_cents')).toBe('2000')
      expect(filtered.query.get('search')).toBe('grill')
    })
  })

  it('asks to replace the cart when adding from a different restaurant (FE-08)', async () => {
    seedCustomer()
    // Pre-load a cart from another restaurant into localStorage.
    const other = { ...restaurant, id: 9, name: 'Gamma' }
    localStorage.setItem(
      'campusbite_cart',
      JSON.stringify({
        restaurant: { ...other, _ownerId: userCustomer.id },
        items: [{ menuItemId: 50, name: 'Gamma Roll', priceCents: 800, quantity: 1 }],
      })
    )
    const otherRestaurant = { ...restaurant, id: 9, name: 'Gamma' }
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['GET', '/restaurants/1', restaurant],
      ['GET', '/restaurants/1/menu', { items: [dish], total: 1, limit: 20, offset: 0 }],
    ])
    const user = userEvent.setup()
    renderPage(Menu, { route: '/restaurants/1', pattern: '/restaurants/:id' })
    await screen.findByText('Grilled Chicken')

    await user.click(screen.getByRole('button', { name: /add to cart/i }))
    const prompt = await screen.findByRole('alert')
    expect(within(prompt).getByText(/replace cart/i)).toBeInTheDocument()
    expect(within(prompt).getByText(/gamma/i)).toBeInTheDocument()

    await user.click(within(prompt).getByRole('button', { name: /replace cart/i }))
    expect(await screen.findByText(/cart replaced/i)).toBeInTheDocument()
    void otherRestaurant
  })
})
