/**
 * T-M11-03 — auth context: user/role/token propagate via context; login
 * stores the token in localStorage; logout clears it; a 401 event clears
 * the user (FE-17).
 *
 * Probe pattern: a null-rendering component that publishes the live context
 * object into a test-held cell. The cell is updated on every re-render, so
 * the test always reads current state.
 */
import { describe, expect, it } from 'vitest'
import { act, render, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext.jsx'
import { tokenStore, fireUnauthorized, resetUnauthorizedGuard, AUTH_EXPIRED_EVENT } from '../../lib/api.js'
import { mockApi, unauthorized } from '../../test/mockApi.js'
import { userCustomer } from '../../test/factories.js'

function renderLiveAuth() {
  const cell = { auth: null }
  function Probe() {
    cell.auth = useAuth()
    return null
  }
  const view = render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  )
  cell.unmount = view.unmount
  return cell
}

/** Seed a "logged in" localStorage snapshot before the provider boots. */
function seedSession(user, token = 'stored-tok') {
  tokenStore.set(token)
  tokenStore.setUser(user)
}

describe('AuthProvider', () => {
  it('boots: a stored token is verified against /auth/me and the DB user wins (T-M11-03)', async () => {
    // The stored snapshot says "owner" but the DB says customer → DB wins.
    seedSession({ ...userCustomer, role: 'restaurant_owner' })
    mockApi([['GET', '/auth/me', userCustomer]])

    const cell = renderLiveAuth()
    await waitFor(() => expect(cell.auth.booting).toBe(false))
    expect(cell.auth.user.role).toBe('customer')
    expect(cell.auth.isCustomer).toBe(true)
    expect(cell.auth.isOwner).toBe(false)
  })

  it('boots clean without a token (no /me call, no spinner)', async () => {
    const { calls } = mockApi([])
    const cell = renderLiveAuth()
    expect(cell.auth.booting).toBe(false)
    expect(cell.auth.user).toBeNull()
    expect(calls.filter((c) => c.path === '/auth/me')).toHaveLength(0)
  })

  it('a stale token that the DB rejects boots signed-out', async () => {
    seedSession(userCustomer)
    mockApi([['GET', '/auth/me', unauthorized('TOKEN_INVALID')]])

    const cell = renderLiveAuth()
    await waitFor(() => expect(cell.auth.booting).toBe(false))
    expect(cell.auth.user).toBeNull()
    expect(tokenStore.get()).toBeNull() // 401 cleared it
  })

  it('login() stores the token in localStorage and sets the user (T-M11-03, FE-03)', async () => {
    mockApi([
      ['POST', '/auth/login', { access_token: 'new-tok', token_type: 'bearer', user: userCustomer }],
    ])
    const cell = renderLiveAuth()

    await act(async () => {
      await cell.auth.login('cust@example.org', 'password-123')
    })
    expect(tokenStore.get()).toBe('new-tok')
    expect(cell.auth.user?.id).toBe(userCustomer.id)
    expect(cell.auth.user?.role).toBe('customer')
  })

  it('login() surfaces a wrong-password 401 without keeping a session', async () => {
    mockApi([
      ['POST', '/auth/login', { status: 401, body: { detail: 'Invalid credentials.', code: 'INVALID_CREDENTIALS' } }],
    ])
    const cell = renderLiveAuth()

    await expect(cell.auth.login('cust@example.org', 'nope')).rejects.toMatchObject({
      status: 401,
      code: 'INVALID_CREDENTIALS',
    })
    expect(cell.auth.user).toBeNull()
  })

  it('logout() clears the token, the cached user, and the context (T-M11-03)', async () => {
    seedSession(userCustomer)
    mockApi([['GET', '/auth/me', userCustomer]])
    const cell = renderLiveAuth()
    await waitFor(() => expect(cell.auth.booting).toBe(false))
    expect(cell.auth.user?.id).toBe(1)

    act(() => {
      cell.auth.logout()
    })
    expect(cell.auth.user).toBeNull()
    expect(tokenStore.get()).toBeNull()
    expect(tokenStore.getUser()).toBeNull()
  })

  it('a 401 mid-session clears the user and fires exactly one event (FE-17, T-M11-07)', async () => {
    seedSession(userCustomer)
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['GET', '/orders', unauthorized()],
    ])
    const cell = renderLiveAuth()
    await waitFor(() => expect(cell.auth.booting).toBe(false))
    expect(cell.auth.user?.id).toBe(1)

    resetUnauthorizedGuard() // module-level loop guard: previous tests fired it
    let events = 0
    const onEvent = () => events += 1
    window.addEventListener(AUTH_EXPIRED_EVENT, onEvent)
    // Simulate an in-flight protected request failing with 401.
    act(() => {
      fireUnauthorized()
    })
    window.removeEventListener(AUTH_EXPIRED_EVENT, onEvent)

    expect(events).toBe(1)
    expect(cell.auth.user).toBeNull()
  })

  it('register() posts email/password/full_name and never a role field (D2)', async () => {
    const { calls } = mockApi([['POST', '/auth/register', { user: userCustomer }]])
    const cell = renderLiveAuth()
    await cell.auth.register('new@example.org', 'password-123', 'New Person')
    expect(calls[0].body).toEqual({
      email: 'new@example.org',
      password: 'password-123',
      full_name: 'New Person',
    })
  })
})
