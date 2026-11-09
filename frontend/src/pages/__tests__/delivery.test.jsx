/**
 * T-M13-06 — partner active list (assigned, not yet completed) + filter.
 * T-M13-07 — partner actions: out-for-delivery / delivered with
 *            confirmation; 409 handled.
 * T-M13-08 — partner history list.
 */
import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { renderPage } from '../../test/harness.jsx'
import { tokenStore } from '../../lib/api.js'
import { mockApi } from '../../test/mockApi.js'
import { userPartner, order } from '../../test/factories.js'
import DeliveryActive from '../DeliveryActive.jsx'
import DeliveryHistory from '../DeliveryHistory.jsx'
import DeliveryOrderDetail from '../DeliveryOrderDetail.jsx'

function seedPartner() {
  tokenStore.set('tok')
  tokenStore.setUser(userPartner)
}

const assigned = order({
  id: 100,
  status: 'ASSIGNED',
  delivery_partner_id: userPartner.id,
})

describe('DeliveryActive (T-M13-06)', () => {
  it('lists the partner own assigned orders (DELV-01) with customer + address', async () => {
    seedPartner()
    mockApi([
      ['GET', '/auth/me', userPartner],
      ['GET', '/delivery/orders', { items: [assigned], total: 1, limit: 20, offset: 0 }],
    ])
    renderPage(DeliveryActive, { route: '/delivery' })

    expect(await screen.findByText(/order #100/i)).toBeInTheDocument()
    expect(screen.getByText('Cust One')).toBeInTheDocument() // customer_name visible
    expect(screen.getByText('Dorm 4, room 12')).toBeInTheDocument()
  })

  it('filters by status through the API (T-M13-06)', async () => {
    seedPartner()
    const { calls } = mockApi([
      ['GET', '/auth/me', userPartner],
      ['GET', '/delivery/orders', { items: [assigned], total: 1, limit: 20, offset: 0 }],
    ])
    const user = userEvent.setup()
    renderPage(DeliveryActive, { route: '/delivery' })
    await screen.findByText(/order #100/i)

    await user.selectOptions(screen.getByLabelText(/^status$/i), 'OUT_FOR_DELIVERY')
    await user.click(screen.getByRole('button', { name: /filter/i }))
    const filtered = calls.filter((c) => c.path === '/delivery/orders').at(-1)
    expect(filtered.query.get('status')).toBe('OUT_FOR_DELIVERY')
  })

  it('shows an empty state when nothing is assigned', async () => {
    seedPartner()
    mockApi([
      ['GET', '/auth/me', userPartner],
      ['GET', '/delivery/orders', { items: [], total: 0, limit: 20, offset: 0 }],
    ])
    renderPage(DeliveryActive, { route: '/delivery' })
    expect(await screen.findByText(/no active deliveries/i)).toBeInTheDocument()
  })
})

describe('DeliveryOrderDetail (T-M13-07)', () => {
  const me = ['GET', '/auth/me', userPartner]

  it('ASSIGNED → confirm → OUT_FOR_DELIVERY (then the delivered action appears)', async () => {
    seedPartner()
    let status = 'ASSIGNED'
    const { calls } = mockApi([
      me,
      [
        'GET',
        '/delivery/orders/100',
        () => ({ ...assigned, status, delivered_at: status === 'DELIVERED' ? '2026-11-08T12:00:00+00:00' : null }),
      ],
      [
        'POST',
        '/orders/100/delivery-status',
        (url, init) => {
          status = JSON.parse(init.body).status
          return { ...assigned, status }
        },
      ],
    ])
    const user = userEvent.setup()
    renderPage(DeliveryOrderDetail, { route: '/delivery/orders/100', pattern: '/delivery/orders/:id' })

    await user.click(await screen.findByRole('button', { name: /^start delivery$/i }))
    await user.click(screen.getByRole('button', { name: /^out for delivery$/i }))
    expect(calls.find((c) => c.path === '/orders/100/delivery-status').body).toEqual({ status: 'OUT_FOR_DELIVERY' })

    // After the reload the delivered action appears; use it.
    await user.click(await screen.findByRole('button', { name: /^mark delivered$/i }))
    await user.click(screen.getByRole('button', { name: /^delivered$/i }))
    const posts = calls.filter((c) => c.path === '/orders/100/delivery-status')
    expect(posts.map((c) => c.body.status)).toEqual(['OUT_FOR_DELIVERY', 'DELIVERED'])
    // delivered_at rendered: the "Delivered" meta row only exists once delivered.
    // (selector: 'dt' excludes the status badge, which shows the same word.)
    expect(await screen.findByText('Delivered', { selector: 'dt' })).toBeInTheDocument()
  })

  it('a 409 (stale/duplicate transition) is surfaced, not swallowed (T-M13-07)', async () => {
    seedPartner()
    mockApi([
      me,
      ['GET', '/delivery/orders/100', assigned],
      [
        'POST',
        '/orders/100/delivery-status',
        { status: 409, body: { detail: 'Only ASSIGNED orders can start delivery.', code: 'INVALID_TRANSITION' } },
      ],
    ])
    const user = userEvent.setup()
    renderPage(DeliveryOrderDetail, { route: '/delivery/orders/100', pattern: '/delivery/orders/:id' })

    await user.click(await screen.findByRole('button', { name: /^start delivery$/i }))
    await user.click(screen.getByRole('button', { name: /^out for delivery$/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/only assigned orders can start delivery/i)
  })

  it('a completed order (DELIVERED) offers no actions', async () => {
    seedPartner()
    mockApi([
      me,
      [
        'GET',
        '/delivery/orders/100',
        { ...assigned, status: 'DELIVERED', delivered_at: '2026-11-08T12:00:00+00:00' },
      ],
    ])
    renderPage(DeliveryOrderDetail, { route: '/delivery/orders/100', pattern: '/delivery/orders/:id' })
    await screen.findByText(/order #100/i)
    expect(screen.queryByRole('button', { name: /start delivery/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /mark delivered/i })).not.toBeInTheDocument()
  })
})

describe('DeliveryHistory (T-M13-08)', () => {
  it('lists past completed assignments with no actions', async () => {
    seedPartner()
    mockApi([
      ['GET', '/auth/me', userPartner],
      [
        'GET',
        '/delivery/history',
        {
          items: [order({ id: 99, status: 'DELIVERED', delivered_at: '2026-11-05T12:00:00+00:00' })],
          total: 1,
          limit: 20,
          offset: 0,
        },
      ],
    ])
    renderPage(DeliveryHistory, { route: '/delivery/history' })

    expect(await screen.findByText(/order #99/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start delivery/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /mark delivered/i })).not.toBeInTheDocument()
  })
})
