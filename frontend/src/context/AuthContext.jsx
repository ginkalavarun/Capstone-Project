import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { api, tokenStore, AUTH_EXPIRED_EVENT } from '../lib/api.js'
import { ROLES } from '../lib/roles.js'

/**
 * Authentication state (FE-03).
 *
 * - The token is stored in localStorage (assignment requirement). It is
 *   re-verified against `GET /auth/me` on load: the database is the source
 *   of truth, so a deactivated user's token stops working (D4).
 * - The user snapshot is also cached locally purely to avoid a login-screen
 *   flash on refresh; the /me response (or a 401) corrects it.
 * - A 401 on ANY request clears the token and fires AUTH_EXPIRED_EVENT
 *   exactly once (loop guard, T-M11-07); this provider then drops the user
 *   and the router sends the user to /login.
 */
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => tokenStore.getUser())
  const [booting, setBooting] = useState(() => Boolean(tokenStore.get()))

  // Verify a stored token on mount.
  useEffect(() => {
    if (!tokenStore.get()) return undefined
    let cancelled = false
    api('GET', '/auth/me')
      .then((u) => {
        if (cancelled) return
        setUser(u)
        tokenStore.setUser(u)
      })
      .catch(() => {
        if (cancelled) return
        setUser(null)
      })
      .finally(() => {
        if (!cancelled) setBooting(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Mid-session 401 → drop the user (the token was already cleared by api.js).
  useEffect(() => {
    const onExpired = () => setUser(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
  }, [])

  const login = useCallback(async (email, password) => {
    const res = await api('POST', '/auth/login', { body: { email, password } })
    tokenStore.set(res.access_token)
    tokenStore.setUser(res.user)
    setUser(res.user)
    return res.user
  }, [])

  const register = useCallback(async (email, password, fullName) => {
    await api('POST', '/auth/register', {
      body: { email, password, full_name: fullName },
    })
  }, [])

  const logout = useCallback(() => {
    tokenStore.set(null)
    tokenStore.setUser(null)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({
      user,
      booting,
      login,
      register,
      logout,
      role: user?.role ?? null,
      isCustomer: user?.role === ROLES.CUSTOMER,
      isOwner: user?.role === ROLES.OWNER,
      isPartner: user?.role === ROLES.PARTNER,
    }),
    [user, booting, login, register, logout]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
