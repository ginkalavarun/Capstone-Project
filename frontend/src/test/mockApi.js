import { vi } from 'vitest'
import { apiBase } from '../lib/api.js'

/**
 * Fetch mock router for tests.
 *
 * Rules are `[method, pathSuffix, outcome]`:
 *   outcome = plain object        → 200 JSON response (the object IS the body)
 *   outcome = null                → 204 (no content)
 *   outcome = { status, body }    → explicit status (401/409/422/503…)
 *   outcome = fn(url, init)       → any of the above, computed per call
 *
 * A plain object is only treated as the `{status, body}` wrapper when it has
 * a `body` key — real response bodies (like orders) carry a `status` FIELD
 * that must not be mistaken for the HTTP status.
 *
 * `calls` is filled with `{ method, path, query, body, headers }` for every
 * request. `path` is relative to the API base (e.g. `/orders`, not
 * `/api/v1/orders`) so tests can assert on the route the app called.
 */
export function mockApi(rules = []) {
  const calls = []
  const base = new URL(apiBase())
  const prefix = base.pathname.replace(/\/$/, '') // e.g. "/api/v1"
  const fetchMock = vi.fn(async (url, init = {}) => {
    const u = new URL(url)
    const method = (init.method || 'GET').toUpperCase()
    const body = init.body ? JSON.parse(init.body) : undefined
    calls.push({
      method,
      path: u.pathname.startsWith(prefix) ? u.pathname.slice(prefix.length) || '/' : u.pathname,
      query: u.searchParams,
      body,
      headers: init.headers,
    })
    for (const [m, suffix, outcome] of rules) {
      if (m !== method) continue
      if (u.pathname !== suffix && !u.pathname.endsWith(suffix)) continue
      const out = typeof outcome === 'function' ? await outcome(url, init) : outcome
      if (out === null || out === undefined) return jsonResponse(null, 204)
      const isWrapper = typeof out === 'object' && 'body' in out
      return jsonResponse(isWrapper ? out.body : out, isWrapper ? (out.status ?? 200) : 200)
    }
    throw new Error(`mockApi: unhandled ${method} ${u.pathname}`)
  })
  globalThis.fetch = fetchMock
  return { fetch: fetchMock, calls }
}

function jsonResponse(body, status) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }
}

/** A 401 response helper (the uniform error body). */
export const unauthorized = (code = 'TOKEN_EXPIRED') => ({
  status: 401,
  body: { detail: 'Your session has expired.', code },
})