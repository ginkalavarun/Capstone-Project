/**
 * CampusBite API client.
 *
 * One thin fetch wrapper used by every page:
 *  - attaches `Authorization: Bearer <token>` when a token is stored
 *    (FE-05; the token lives in localStorage per the assignment brief —
 *    the documented trade-off: convenient, but readable by any script on
 *    the origin, which is why ALL real authorization still happens in the
 *    backend, and a 401 mid-session logs the user out exactly once);
 *  - parses the uniform error body `{"detail", "code"}` (contract §1) into
 *    an `ApiError` with a stable `code` the UI branches on;
 *  - on 401 clears the stored token and fires one `campusbite:auth-expired`
 *    event per session (loop guard, T-M11-07) — AuthProvider clears the
 *    user state, RequireAuth redirects to /login, and nothing can loop.
 */
const TOKEN_KEY = 'campusbite_token'
const USER_KEY = 'campusbite_user'

export const AUTH_EXPIRED_EVENT = 'campusbite:auth-expired'

/** Base URL of the backend API (no secrets — FE env, D23). */
export function apiBase() {
  return import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
}

/** Uniform API error (contract §1): `code` is a stable machine token. */
export class ApiError extends Error {
  constructor(status, detail, code) {
    super(detail || `Request failed with status ${status}.`)
    this.name = 'ApiError'
    this.status = status // 0 = network failure (no response at all)
    this.code = code
  }
}

/** localStorage-backed token + user snapshot (the brief requires localStorage). */
export const tokenStore = {
  get() {
    return localStorage.getItem(TOKEN_KEY)
  },
  set(token) {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  },
  getUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY))
    } catch {
      return null
    }
  },
  setUser(user) {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
    else localStorage.removeItem(USER_KEY)
  },
}

// T-M11-07: fire the expiry event at most once per page session.
let unauthorizedFired = false

export function resetUnauthorizedGuard() {
  unauthorizedFired = false
}

/** Called on every 401: clears the token and notifies the app once. */
export function fireUnauthorized() {
  tokenStore.set(null)
  tokenStore.setUser(null)
  if (!unauthorizedFired) {
    unauthorizedFired = true
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT))
  }
}

function buildUrl(path, params) {
  let url = `${apiBase()}${path}`
  if (params) {
    const qs = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== '') qs.set(key, value)
    }
    const s = qs.toString()
    if (s) url += `?${s}`
  }
  return url
}

/**
 * Perform a request and return the parsed JSON body (or `null` for 204).
 * Throws `ApiError` for non-2xx responses and network failures.
 *
 * On success the response `status` is attached to the returned object as a
 * non-enumerable property so the rare callers that must distinguish e.g.
 * 201 (created) from 200 (idempotent retry) can — without polluting JSON.
 */
export async function api(method, path, { body, params } = {}) {
  const headers = {}
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let res
  try {
    res = await fetch(buildUrl(path, params), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server. Is the backend running?', 'NETWORK_ERROR')
  }

  if (res.status === 401) fireUnauthorized()

  if (res.status === 204) return null

  let payload = null
  try {
    payload = await res.json()
  } catch {
    payload = null
  }
  const detail =
    typeof payload?.detail === 'string' && payload.detail
      ? payload.detail
      : `Request failed with status ${res.status}.`

  if (!res.ok) throw new ApiError(res.status, detail, payload?.code || 'UNKNOWN')

  if (payload && typeof payload === 'object') {
    // Work on a copy: the response body is the caller's object, and a body
    // that ALREADY has a `status` field (orders do) keeps its domain value.
    // The HTTP status is attached as a non-enumerable `status` only when the
    // body has none of its own — callers that must tell 201 (created) from
    // 200 (idempotent retry) can read it without polluting the JSON shape.
    const copy = structuredClone(payload)
    if (!Object.hasOwn(copy, 'status')) {
      Object.defineProperty(copy, 'status', { value: res.status, enumerable: false })
    }
    return copy
  }
  return payload
}

export const get = (path, params) => api('GET', path, { params })
export const post = (path, body) => api('POST', path, { body })
export const put = (path, body) => api('PUT', path, { body })
export const del = (path) => api('DELETE', path)
