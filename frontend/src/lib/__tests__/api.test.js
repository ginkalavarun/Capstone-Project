/**
 * T-M11-05 — Bearer header attached; uniform error parsing.
 * T-M11-07 — a 401 mid-session clears the token and redirects exactly once
 * (no endless loop).
 */
import { describe, expect, it, vi } from 'vitest'
import { mockApi, unauthorized } from '../../test/mockApi.js'
import {
  api,
  tokenStore,
  fireUnauthorized,
  resetUnauthorizedGuard,
  AUTH_EXPIRED_EVENT,
  ApiError,
} from '../api.js'

describe('api client', () => {
  vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000/api/v1')

  it('attaches Authorization: Bearer <token> to protected requests (T-M11-05)', async () => {
    const { calls } = mockApi([['GET', '/auth/me', { id: 1, role: 'customer' }]])
    tokenStore.set('tok-123')

    const user = await api('GET', '/auth/me')
    expect(user.role).toBe('customer')
    expect(calls[0].headers.Authorization).toBe('Bearer tok-123')
  })

  it('sends no Authorization header when no token is stored (public catalog, D16)', async () => {
    const { calls } = mockApi([['GET', '/restaurants', { items: [], total: 0 }]])
    tokenStore.set(null)

    await api('GET', '/restaurants')
    expect(calls[0].headers.Authorization).toBeUndefined()
  })

  it('parses the uniform {"detail","code"} error body into ApiError (T-M11-05)', async () => {
    mockApi([
      ['POST', '/orders', { status: 409, body: { detail: 'Same key, different payload.', code: 'IDEMPOTENCY_MISMATCH' } }],
    ])
    tokenStore.set('tok')

    await expect(api('POST', '/orders', { body: {} })).rejects.toMatchObject({
      name: 'ApiError',
      status: 409,
      code: 'IDEMPOTENCY_MISMATCH',
      message: 'Same key, different payload.',
    })
  })

  it('passes query params through and drops empty values', async () => {
    const { calls } = mockApi([['GET', '/orders', { items: [], total: 0 }]])
    tokenStore.set('tok')

    await api('GET', '/orders', { params: { status: '', date_from: '2026-11-01T00:00:00', limit: 20 } })
    const qs = calls[0].query
    expect([...qs.entries()]).toEqual([
      ['date_from', '2026-11-01T00:00:00'],
      ['limit', '20'],
    ])
  })

  it('throws NETWORK_ERROR when the server is unreachable', async () => {
    globalThis.fetch = vi.fn(() => Promise.reject(new Error('boom')))
    await expect(api('GET', '/restaurants')).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
      code: 'NETWORK_ERROR',
    })
  })

  it('returns the response status as a non-enumerable property (201-vs-200, D34)', async () => {
    mockApi([['POST', '/orders', { id: 7, status: 201, body: { id: 7 } }]])
    tokenStore.set('tok')

    const created = await api('POST', '/orders', { body: {} })
    expect(created.status).toBe(201)
    // …but it does not pollute serialization
    expect(JSON.stringify(created)).toBe('{"id":7}')
  })

  it('clears the token and fires the expiry event EXACTLY ONCE per 401 (T-M11-07)', async () => {
    mockApi([['GET', '/auth/me', unauthorized()]])
    tokenStore.set('tok-123')
    resetUnauthorizedGuard()

    let events = 0
    const onEvent = () => events += 1
    window.addEventListener(AUTH_EXPIRED_EVENT, onEvent)
    try {
      await api('GET', '/auth/me').catch(() => {})
      await api('GET', '/auth/me').catch(() => {}) // second 401 — same session
      expect(events).toBe(1)
      expect(tokenStore.get()).toBeNull()
    } finally {
      window.removeEventListener(AUTH_EXPIRED_EVENT, onEvent)
    }
  })

  it('fireUnauthorized() clears both the token and the cached user', () => {
    tokenStore.set('tok')
    tokenStore.setUser({ id: 1, full_name: 'A', role: 'customer' })
    resetUnauthorizedGuard()

    let fired = 0
    const onEvent = () => fired += 1
    window.addEventListener(AUTH_EXPIRED_EVENT, onEvent)
    try {
      fireUnauthorized()
      expect(fired).toBe(1)
      expect(tokenStore.get()).toBeNull()
      expect(tokenStore.getUser()).toBeNull()
    } finally {
      window.removeEventListener(AUTH_EXPIRED_EVENT, onEvent)
    }
  })

  it('ApiError carries the backend sentence as the message', () => {
    const e = new ApiError(409, 'Invalid transition from ACCEPTED.', 'INVALID_TRANSITION')
    expect(e.message).toBe('Invalid transition from ACCEPTED.')
    expect(e.status).toBe(409)
    expect(e.code).toBe('INVALID_TRANSITION')
  })
})
