/**
 * T-M12-06 — dashboard: list + status/date filters + pagination.
 * T-M12-07 — order detail: renders current status + timeline.
 * T-M12-08 — cancel: only while PLACED; confirms; handles 409.
 * T-M12-09 — refund request: only DELIVERED; renders pending/rejected/
 *            approved states; one request per order (D28).
 * FE-10    — review: shown once delivered; 409 REVIEW_EXISTS handled.
 */
import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { renderPage } from '../../test/harness.jsx'
import { tokenStore } from '../../lib/api.js'
import { mockApi } from '../../test/mockApi.js'
import { userCustomer, order } from '../../test/factories.js'
import CustomerOrders from '../CustomerOrders.jsx'
import CustomerOrderDetail from '../CustomerOrderDetail.jsx'

function seedCustomer() {
  tokenStore.set('tok')
  tokenStore.setUser(userCustomer)
}

describe('CustomerOrders (T-M12-06)', () => {
  it('lists orders and sends status + date filters to the server', async () => {
    seedCustomer()
    const { calls } = mockApi([
      ['GET', '/auth/me', userCustomer],
      ['GET', '/orders', { items: [order({ id: 100 }), order({ id: 101, status: 'DELIVERED' })], total: 2, limit: 20, offset: 0 }],
    ])
    const user = userEvent.setup()
    renderPage(CustomerOrders, { route: '/orders' })

    // The card title spans two elements (name + "· order #N"), so match the span.
    expect(await screen.findByText(/order #100/i)).toBeInTheDocument()
    expect(screen.getByText(/order #101/i)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText(/^status$/i), 'DELIVERED')
    await user.type(screen.getByLabelText(/^from$/i), '2026-11-01T00:00')
    await user.click(screen.getByRole('button', { name: /filter/i }))

    const filtered = calls.filter((c) => c.path === '/orders').at(-1)
    expect(filtered.query.get('status')).toBe('DELIVERED')
    expect(filtered.query.get('date_from')).toBe('2026-11-01T00:00')
  })

  it('shows an empty state and pagination over the envelope', async () => {
    seedCustomer()
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['GET', '/orders', { items: [], total: 0, limit: 20, offset: 0 }],
    ])
    renderPage(CustomerOrders, { route: '/orders' })
    expect(await screen.findByText(/no orders found/i)).toBeInTheDocument()
  })
})

describe('CustomerOrderDetail', () => {
  const base = ['GET', '/auth/me', userCustomer]

  it('renders the timeline with the current status highlighted (T-M12-07)', async () => {
    seedCustomer()
    mockApi([base, ['GET', '/orders/100', order({ id: 100, status: 'PREPARING' })]])
    renderPage(CustomerOrderDetail, { route: '/orders/100', pattern: '/orders/:id' })

    const timeline = await screen.findByRole('list', { name: /order progress/i })
    // The steps render humanized ("Preparing"), so match case-insensitively.
    expect(within(timeline).getByText(/preparing/i).closest('li')).toHaveClass('current')
    expect(within(timeline).getByText(/placed/i).closest('li')).toHaveClass('done')
  })

  it('offers cancellation only while PLACED (T-M12-08)', async () => {
    seedCustomer()
    mockApi([base, ['GET', '/orders/100', order({ id: 100, status: 'ACCEPTED' })]])
    renderPage(CustomerOrderDetail, { route: '/orders/100', pattern: '/orders/:id' })
    await screen.findByText(/order #100/i)
    expect(screen.queryByRole('button', { name: /cancel order/i })).not.toBeInTheDocument()
  })

  it('cancel: confirms, then shows the D29 reversal notice (T-M12-08)', async () => {
    seedCustomer()
    const { calls } = mockApi([
      base,
      ['GET', '/orders/100', order({ id: 100, status: 'PLACED' })],
      ['POST', '/orders/100/cancel', order({ id: 100, status: 'CANCELLED', payment_status: 'refunded' })],
    ])
    const user = userEvent.setup()
    renderPage(CustomerOrderDetail, { route: '/orders/100', pattern: '/orders/:id' })

    await user.click(await screen.findByRole('button', { name: /cancel order/i }))
    await user.click(screen.getByRole('button', { name: /yes, cancel/i }))

    const call = calls.find((c) => c.path === '/orders/100/cancel')
    expect(call.method).toBe('POST')
    expect(await screen.findByText(/mock payment was reversed/i)).toBeInTheDocument()
  })

  it('cancel: a 409 (order progressed meanwhile) is surfaced, not swallowed (T-M12-08)', async () => {
    seedCustomer()
    mockApi([
      base,
      ['GET', '/orders/100', order({ id: 100, status: 'PLACED' })],
      [
        'POST',
        '/orders/100/cancel',
        { status: 409, body: { detail: 'Only PLACED orders can be cancelled.', code: 'INVALID_TRANSITION' } },
      ],
    ])
    const user = userEvent.setup()
    renderPage(CustomerOrderDetail, { route: '/orders/100', pattern: '/orders/:id' })

    await user.click(await screen.findByRole('button', { name: /cancel order/i }))
    await user.click(screen.getByRole('button', { name: /yes, cancel/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/only placed orders can be cancelled/i)
  })

  it('refund: the reason form appears only for DELIVERED orders (T-M12-09)', async () => {
    seedCustomer()
    mockApi([base, ['GET', '/orders/100', order({ id: 100, status: 'DELIVERED', delivered_at: '2026-11-08T10:00:00+00:00' })]])
    renderPage(CustomerOrderDetail, { route: '/orders/100', pattern: '/orders/:id' })

    expect(await screen.findByLabelText(/why do you want a refund/i)).toBeInTheDocument()
  })

  it('refund: pending / rejected / approved states render without a new form (D28)', async () => {
    // D30: approval moves the order to REFUNDED — the UI must still render it.
    for (const [orderStatus, refundStatus, text] of [
      ['DELIVERED', 'pending', /pending/i],
      ['DELIVERED', 'rejected', /one request per order/i],
      ['REFUNDED', 'approved', /refund was approved/i],
    ]) {
      seedCustomer()
      mockApi([
        base,
        [
          'GET',
          '/orders/100',
          order({ id: 100, status: orderStatus, refund_status: refundStatus, payment_status: refundStatus === 'approved' ? 'refunded' : 'mock_paid', delivered_at: '2026-11-08T10:00:00+00:00' }),
        ],
      ])
      const view = renderPage(CustomerOrderDetail, { route: '/orders/100', pattern: '/orders/:id' })
      // Wait for the order to load (the loading hint also uses role=status and
      // is unmounted once the data arrives), then check the refund state line.
      await screen.findByText(/order #100/i)
      const statusRegions = screen.getAllByRole('status')
      expect(statusRegions.at(-1)).toHaveTextContent(text)
      expect(screen.queryByLabelText(/why do you want a refund/i)).not.toBeInTheDocument()
      view.unmount()
    }
  })

  it('refund request submits the bounded reason and shows pending (T-M12-09)', async () => {
    seedCustomer()
    let requested = false // flips when the POST below is served
    const { calls } = mockApi([
      base,
      [
        'GET',
        '/orders/100',
        () =>
          // Re-loads show the pending state once the request was accepted.
          order({
            id: 100,
            status: 'DELIVERED',
            refund_status: requested ? 'pending' : null,
            delivered_at: '2026-11-08T10:00:00+00:00',
          }),
      ],
      [
        'POST',
        '/orders/100/refund-request',
        (url, init) => {
          requested = true
          return {
            id: 9,
            order_id: 100,
            status: 'pending',
            reason: JSON.parse(init.body).reason,
            requested_at: 'x',
            decided_at: null,
          }
        },
      ],
    ])
    const user = userEvent.setup()
    renderPage(CustomerOrderDetail, { route: '/orders/100', pattern: '/orders/:id' })

    await user.type(await screen.findByLabelText(/why do you want a refund/i), 'Arrived cold.')
    await user.click(screen.getByRole('button', { name: /request refund/i }))

    expect(await screen.findByText(/will approve or reject/i)).toBeInTheDocument()
    const call = calls.find((c) => c.path === '/orders/100/refund-request')
    expect(call.body).toEqual({ reason: 'Arrived cold.' })
  })

  it('review: form appears once delivered; a 409 REVIEW_EXISTS is handled (FE-10, D31, REV-02)', async () => {
    seedCustomer()
    mockApi([
      base,
      ['GET', '/orders/100', () => order({ id: 100, status: 'DELIVERED', delivered_at: '2026-11-08T10:00:00+00:00' })],
      [
        'POST',
        '/orders/100/review',
        { status: 409, body: { detail: 'This order already has a review.', code: 'REVIEW_EXISTS' } },
      ],
    ])
    const user = userEvent.setup()
    renderPage(CustomerOrderDetail, { route: '/orders/100', pattern: '/orders/:id' })

    // The detail (and with it the review form) loads asynchronously.
    await user.selectOptions(await screen.findByLabelText(/^rating$/i), '4')
    await user.type(screen.getByLabelText(/comment/i), 'Tasty!')
    await user.click(screen.getByRole('button', { name: /submit review/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/already has a review/i)
  })

  it('review is hidden for orders that were never delivered (D31)', async () => {
    seedCustomer()
    mockApi([base, ['GET', '/orders/100', order({ id: 100, status: 'READY', delivered_at: null })]])
    renderPage(CustomerOrderDetail, { route: '/orders/100', pattern: '/orders/:id' })
    await screen.findByText(/order #100/i)
    expect(screen.queryByLabelText(/^rating$/i)).not.toBeInTheDocument()
  })
})
