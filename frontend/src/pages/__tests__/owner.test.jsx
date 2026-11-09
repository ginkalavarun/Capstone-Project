/**
 * T-M13-01 — owner orders: list + filters + pagination (DASH-01).
 * T-M13-02 — accept/prep/ready actions appear per status; assignment from
 *            the protected partner listing.
 * T-M13-03 — refund approve/reject with confirmation.
 * T-M13-04 — reminders list + local dismiss.
 * T-M13-05 — stats cards + menu management (create/edit/toggle).
 */
import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { renderPage } from '../../test/harness.jsx'
import { tokenStore } from '../../lib/api.js'
import { mockApi } from '../../test/mockApi.js'
import { userOwner, restaurant, dish, order, reminder, stats } from '../../test/factories.js'
import OwnerOrders from '../OwnerOrders.jsx'
import OwnerOrderDetail from '../OwnerOrderDetail.jsx'
import OwnerMenu from '../OwnerMenu.jsx'
import OwnerReminders from '../OwnerReminders.jsx'
import OwnerStats from '../OwnerStats.jsx'

function seedOwner() {
  tokenStore.set('tok')
  tokenStore.setUser(userOwner)
}

describe('OwnerOrders (T-M13-01)', () => {
  it('lists the owner own restaurant orders with filters (DASH-01, D24)', async () => {
    seedOwner()
    const { calls } = mockApi([
      ['GET', '/auth/me', userOwner],
      [
        'GET',
        '/owner/orders',
        { items: [order({ id: 100 }), order({ id: 101, status: 'READY' })], total: 2, limit: 20, offset: 0 },
      ],
    ])
    const user = userEvent.setup()
    renderPage(OwnerOrders, { route: '/owner/orders' })

    // The card title spans two elements (name + "· order #N"), so match the span.
    expect(await screen.findByText(/order #100/i)).toBeInTheDocument()
    expect(screen.getByText(/order #101/i)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText(/^status$/i), 'READY')
    await user.click(screen.getByRole('button', { name: /filter/i }))
    const filtered = calls.filter((c) => c.path === '/owner/orders').at(-1)
    expect(filtered.query.get('status')).toBe('READY')
  })

  it('never accepts a restaurant id (own restaurant only, D24)', async () => {
    seedOwner()
    const { calls } = mockApi([
      ['GET', '/auth/me', userOwner],
      ['GET', '/owner/orders', { items: [], total: 0, limit: 20, offset: 0 }],
    ])
    renderPage(OwnerOrders, { route: '/owner/orders' })
    await screen.findByText(/no orders yet/i)
    expect(calls.find((c) => c.path === '/owner/orders').query.get('restaurant_id')).toBeNull()
  })
})

describe('OwnerOrderDetail — transitions (T-M13-02)', () => {
  const me = ['GET', '/auth/me', userOwner]

  it('shows exactly one action per the current status (PLACED → Accept)', async () => {
    seedOwner()
    mockApi([me, ['GET', '/orders/100', order({ id: 100, status: 'PLACED' })], ['GET', '/delivery-partners', []]])
    renderPage(OwnerOrderDetail, { route: '/owner/orders/100', pattern: '/owner/orders/:id' })

    expect(await screen.findByRole('button', { name: /^accept$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start preparing/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /mark ready/i })).not.toBeInTheDocument()
  })

  it('accept confirms then calls the endpoint and reloads (409-safe)', async () => {
    seedOwner()
    const { calls } = mockApi([
      me,
      [
        'GET',
        '/orders/100',
        (url) =>
          order({ id: 100, status: url.includes('accept') ? 'ACCEPTED' : 'PLACED' }),
      ],
      ['POST', '/orders/100/accept', order({ id: 100, status: 'ACCEPTED' })],
      ['GET', '/delivery-partners', []],
    ])
    const user = userEvent.setup()
    renderPage(OwnerOrderDetail, { route: '/owner/orders/100', pattern: '/owner/orders/:id' })

    await user.click(await screen.findByRole('button', { name: /^accept$/i }))
    await user.click(screen.getByRole('button', { name: /^accept order/i })) // the confirm step

    const call = calls.find((c) => c.path === '/orders/100/accept')
    expect(call).toBeDefined()
    expect(call.method).toBe('POST')
  })

  it('a 409 INVALID_TRANSITION (owner clicked a stale state) is surfaced', async () => {
    seedOwner()
    mockApi([
      me,
      ['GET', '/orders/100', order({ id: 100, status: 'PLACED' })],
      [
        'POST',
        '/orders/100/accept',
        { status: 409, body: { detail: 'Only PLACED orders can be accepted.', code: 'INVALID_TRANSITION' } },
      ],
      ['GET', '/delivery-partners', []],
    ])
    const user = userEvent.setup()
    renderPage(OwnerOrderDetail, { route: '/owner/orders/100', pattern: '/owner/orders/:id' })

    await user.click(await screen.findByRole('button', { name: /^accept$/i }))
    await user.click(screen.getByRole('button', { name: /^accept order/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/only placed orders can be accepted/i)
  })

  it('READY orders offer the protected partner listing for assignment', async () => {
    seedOwner()
    const { calls } = mockApi([
      me,
      ['GET', '/orders/100', order({ id: 100, status: 'READY' })],
      ['GET', '/delivery-partners', [{ id: 3, full_name: 'Partner One' }, { id: 4, full_name: 'Partner Two' }]],
      ['POST', '/orders/100/assign', order({ id: 100, status: 'ASSIGNED', delivery_partner_id: 3 })],
    ])
    const user = userEvent.setup()
    renderPage(OwnerOrderDetail, { route: '/owner/orders/100', pattern: '/owner/orders/:id' })

    const select = await screen.findByLabelText(/^assign to$/i)
    // The partner listing loads after the order does — wait for the option
    // instead of racing the async fetch.
    await screen.findByRole('option', { name: /partner two/i })
    await user.selectOptions(select, '4')
    await user.click(screen.getByRole('button', { name: /^assign$/i }))
    await user.click(screen.getByRole('button', { name: /^confirm assignment$/i }))

    const call = calls.find((c) => c.path === '/orders/100/assign')
    expect(call.body).toEqual({ delivery_partner_id: 4 })
  })
})

describe('OwnerOrderDetail — refund decision (T-M13-03)', () => {
  const me = ['GET', '/auth/me', userOwner]

  it('pending requests expose Approve/Reject; approve confirms and calls the endpoint', async () => {
    seedOwner()
    const { calls } = mockApi([
      me,
      ['GET', '/orders/100', order({ id: 100, status: 'DELIVERED', refund_status: 'pending', refund_reason: 'cold food', delivered_at: 'x' })],
      ['POST', '/orders/100/refund/approve', order({ id: 100, status: 'REFUNDED', refund_status: 'approved', payment_status: 'refunded' })],
      ['GET', '/delivery-partners', []],
    ])
    const user = userEvent.setup()
    renderPage(OwnerOrderDetail, { route: '/owner/orders/100', pattern: '/owner/orders/:id' })

    expect(await screen.findByText(/cold food/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /approve refund/i }))
    await user.click(screen.getByRole('button', { name: /approve \+ refund/i }))

    const call = calls.find((c) => c.path === '/orders/100/refund/approve')
    expect(call).toBeDefined()
    expect(await screen.findByText(/refund approved/i)).toBeInTheDocument()
  })

  it('reject leaves the order as-is and a double decision shows the 409', async () => {
    seedOwner()
    const { calls } = mockApi([
      me,
      ['GET', '/orders/100', order({ id: 100, status: 'DELIVERED', refund_status: 'pending', refund_reason: 'cold food', delivered_at: 'x' })],
      [
        'POST',
        '/orders/100/refund/reject',
        { status: 409, body: { detail: 'This refund request was already decided.', code: 'REFUND_ALREADY_DECIDED' } },
      ],
      ['GET', '/delivery-partners', []],
    ])
    const user = userEvent.setup()
    renderPage(OwnerOrderDetail, { route: '/owner/orders/100', pattern: '/owner/orders/:id' })

    await user.click(await screen.findByRole('button', { name: /reject/i }))
    await user.click(screen.getByRole('button', { name: /reject refund/i }))

    expect(calls.find((c) => c.path === '/orders/100/refund/reject')).toBeDefined()
    expect(await screen.findByRole('alert')).toHaveTextContent(/already decided/i)
  })

  it('decided requests (approved/rejected) render the outcome, no buttons', async () => {
    seedOwner()
    mockApi([
      me,
      ['GET', '/orders/100', order({ id: 100, status: 'REFUNDED', refund_status: 'approved', payment_status: 'refunded', delivered_at: 'x' })],
      ['GET', '/delivery-partners', []],
    ])
    renderPage(OwnerOrderDetail, { route: '/owner/orders/100', pattern: '/owner/orders/:id' })
    await screen.findByText(/refund paid out/i)
    expect(screen.queryByRole('button', { name: /approve refund/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument()
  })
})

describe('OwnerReminders (T-M13-04)', () => {
  it('lists open stale orders with order links and a local dismiss', async () => {
    seedOwner()
    mockApi([
      ['GET', '/auth/me', userOwner],
      ['GET', '/owner/reminders', { items: [reminder], total: 1, limit: 50, offset: 0 }],
    ])
    const user = userEvent.setup()
    renderPage(OwnerReminders, { route: '/owner/reminders' })

    expect(await screen.findByText(/order #100/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /order #100/i })).toHaveAttribute('href', '/owner/orders/100')

    await user.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(screen.queryByText(/order #100/i)).not.toBeInTheDocument() // hidden locally
  })

  it('shows an empty state when nothing is overdue', async () => {
    seedOwner()
    mockApi([
      ['GET', '/auth/me', userOwner],
      ['GET', '/owner/reminders', { items: [], total: 0, limit: 50, offset: 0 }],
    ])
    renderPage(OwnerReminders, { route: '/owner/reminders' })
    expect(await screen.findByText(/nothing overdue/i)).toBeInTheDocument()
  })
})

describe('OwnerStats (T-M13-05, D35)', () => {
  it('renders the documented metric set with cents formatted as EUR', async () => {
    seedOwner()
    mockApi([
      ['GET', '/auth/me', userOwner],
      ['GET', '/owner/stats', stats],
    ])
    renderPage(OwnerStats, { route: '/owner/stats' })

    expect(await screen.findByText('Gross (mock-paid)')).toBeInTheDocument()
    expect(screen.getByText('€106.00')).toBeInTheDocument() // gross
    expect(screen.getAllByText('€26.50')).toHaveLength(2) // refunded AND avg order value (both 2650)
    expect(screen.getByText('€79.50')).toBeInTheDocument() // net
    // The D35 wording: mock value is not blindly called revenue.
    expect(screen.getByText(/revenue/i)).toBeInTheDocument()
  })
})

describe('OwnerMenu (T-M13-05)', () => {
  const me = ['GET', '/auth/me', userOwner]

  it('loads the owner own restaurant, then its menu (batch-8 enablement endpoint)', async () => {
    seedOwner()
    const { calls } = mockApi([
      me,
      ['GET', '/owner/restaurant', restaurant],
      ['GET', '/restaurants/1/menu', { items: [dish], total: 1, limit: 100, offset: 0 }],
    ])
    renderPage(OwnerMenu, { route: '/owner/menu' })

    expect(await screen.findByText('Grilled Chicken')).toBeInTheDocument()
    expect(calls.some((c) => c.path === '/owner/restaurant')).toBe(true)
    expect(calls.some((c) => c.path === '/restaurants/1/menu')).toBe(true)
  })

  it('creates a dish with the euro→cents conversion', async () => {
    seedOwner()
    const { calls } = mockApi([
      me,
      ['GET', '/owner/restaurant', restaurant],
      [
        'GET',
        '/restaurants/1/menu',
        (url, init) =>
          init?.method === 'POST' ? dish : { items: [dish], total: 1, limit: 100, offset: 0 },
      ],
      [
        'POST',
        '/restaurants/1/menu',
        { ...dish, id: 12, name: 'Burger', price_cents: 990 },
      ],
    ])
    const user = userEvent.setup()
    renderPage(OwnerMenu, { route: '/owner/menu' })

    await user.type(await screen.findByLabelText(/^name$/i), 'Burger')
    await user.type(screen.getByLabelText(/^price \(€\)$/i), '9.90')
    await user.click(screen.getByRole('button', { name: /add dish/i }))

    const call = calls.find((c) => c.method === 'POST' && c.path === '/restaurants/1/menu')
    expect(call.body).toMatchObject({ name: 'Burger', price_cents: 990, available: true })
  })

  it('soft-removes (never hard-deletes) a dish (D32) and can re-enable it', async () => {
    seedOwner()
    const gone = { ...dish, available: false }
    // The list is stateful: it starts AVAILABLE, flips to `gone` once the
    // soft-remove DELETE is served, and flips back on the re-enable PUT.
    let available = true
    const { calls } = mockApi([
      me,
      ['GET', '/owner/restaurant', restaurant],
      [
        'GET',
        '/restaurants/1/menu',
        () => ({ items: [available ? dish : gone], total: 1, limit: 100, offset: 0 }),
      ],
      [
        'DELETE',
        '/menu-items/10',
        () => {
          available = false // soft remove: the backend sets available=false
          return null // 204 no content
        },
      ],
      [
        'PUT',
        '/menu-items/10',
        () => {
          available = true
          return dish
        },
      ],
    ])
    const user = userEvent.setup()
    renderPage(OwnerMenu, { route: '/owner/menu' })

    await screen.findByText('Grilled Chicken')
    await user.click(await screen.findByRole('button', { name: /mark unavailable/i }))
    const delCall = calls.find((c) => c.method === 'DELETE' && c.path === '/menu-items/10')
    expect(delCall).toBeDefined() // soft remove = DELETE → available=false

    await user.click(await screen.findByRole('button', { name: /re-enable/i }))
    const putCall = calls.find((c) => c.method === 'PUT' && c.path === '/menu-items/10')
    expect(putCall.body).toEqual({ available: true }) // partial update
  })
})
