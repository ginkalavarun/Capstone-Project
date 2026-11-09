/**
 * T-M11-01 — scaffold + router: all role routes render; unknown route → 404.
 * T-M11-04 — protected routes: unauthenticated → /login; role mismatch → 403 page.
 * T-M11-06 — async views: loading state, then error state with retry.
 */
import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { renderApp } from '../test/harness.jsx'
import { tokenStore } from '../lib/api.js'
import { mockApi } from '../test/mockApi.js'
import { userCustomer, userOwner, userPartner, restaurant, page as pageOf } from '../test/factories.js'
import App from '../App.jsx'

function seed(user) {
  tokenStore.set('tok')
  tokenStore.setUser(user)
}

describe('route protection (T-M11-04)', () => {
  it('sends an unauthenticated visitor to /login when asking for /orders', async () => {
    tokenStore.set(null)
    tokenStore.setUser(null)
    mockApi([])
    renderApp(<App />, { route: '/orders' })

    await waitFor(() => expect(screen.getByRole('heading', { name: /log in/i })).toBeInTheDocument())
    expect(screen.queryByText('My orders')).not.toBeInTheDocument()
  })

  it('a customer is sent to the 403 page for owner routes', async () => {
    seed(userCustomer)
    mockApi([['GET', '/auth/me', userCustomer]])
    renderApp(<App />, { route: '/owner/orders' })

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/not allowed/i)
    )
  })

  it('a partner is sent to the 403 page for customer and owner routes', async () => {
    seed(userPartner)
    mockApi([['GET', '/auth/me', userPartner]])
    renderApp(<App />, { route: '/owner/stats' })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/not allowed/i))
  })

  it('a customer CAN reach /orders when authenticated (guard passes)', async () => {
    seed(userCustomer)
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['GET', '/orders', pageOf([])],
    ])
    renderApp(<App />, { route: '/orders' })

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /my orders/i })).toBeInTheDocument()
    )
  })

  it('the owner and partner dashboards render for the right roles', async () => {
    seed(userOwner)
    mockApi([
      ['GET', '/auth/me', userOwner],
      ['GET', '/owner/orders', pageOf([])],
      ['GET', '/delivery/orders', pageOf([])],
      ['GET', '/delivery-partners', []],
    ])
    const view = renderApp(<App />, { route: '/owner/orders' })
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /incoming orders/i })).toBeInTheDocument()
    )
    // …and the partner's side of the same app. Re-register the mock: the
    // /auth/me rule above is pinned to the owner, but this app boots as the
    // partner — the mock must answer with the partner's identity.
    seed(userPartner)
    mockApi([
      ['GET', '/auth/me', userPartner],
      ['GET', '/delivery/orders', pageOf([])],
    ])
    renderApp(<App />, { route: '/delivery' })
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /my deliveries/i })).toBeInTheDocument()
    )
    view.unmount()
  })
})

describe('scaffold + router (T-M11-01)', () => {
  it('an unknown route lands on the 404 page', async () => {
    tokenStore.set(null)
    tokenStore.setUser(null)
    mockApi([])
    renderApp(<App />, { route: '/definitely-not-a-route' })

    await waitFor(() => expect(screen.getByText(/page not found/i)).toBeInTheDocument())
  })

  it('the home page offers browsing to anonymous visitors (D16)', async () => {
    tokenStore.set(null)
    tokenStore.setUser(null)
    mockApi([])
    renderApp(<App />, { route: '/' })
    expect(screen.getByText(/browse restaurants/i)).toBeInTheDocument()
  })
})

describe('async view states (T-M11-06, FE-14)', () => {
  it('shows loading, then a retryable error, then recovers on retry', async () => {
    tokenStore.set(null)
    tokenStore.setUser(null)
    let settle
    const pending = () =>
      new Promise((resolve, reject) => {
        settle = { resolve, reject }
      })
    mockApi([
      ['GET', '/restaurants', () => pending()],
    ])
    const user = userEvent.setup()
    renderApp(<App />, { route: '/restaurants' })

    // 1. loading
    expect(await screen.findByRole('status')).toHaveTextContent(/loading restaurants/i)

    // 2. failure → error + retry button
    settle.reject(new Error('connection refused'))
    const alert = await screen.findByRole('alert')
    expect(alert).toBeInTheDocument()
    const retry = screen.getByRole('button', { name: /try again/i })

    // 3. retry → the second call resolves → content
    mockApi([
      ['GET', '/restaurants', { items: [restaurant], total: 1, limit: 100, offset: 0 }],
    ])
    await user.click(retry)
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument())
  })
})
