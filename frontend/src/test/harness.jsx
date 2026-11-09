import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { useEffect } from 'react'
import { AuthProvider } from '../context/AuthContext.jsx'
import { CartProvider } from '../context/CartContext.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { useCart } from '../context/CartContext.jsx'

/**
 * Test harness: the full provider stack inside a MemoryRouter.
 *
 * - `route` picks the initial URL (for redirects / guards).
 * - `pattern` (optional) is a route pattern such as `/orders/:id`. When
 *   given, the rendered element is mounted inside a `<Routes>` with that
 *   pattern so `useParams` works — a bare page render has no matched
 *   route and would see `id === undefined`.
 *   Pass it for pages that read URL params (menu, order details).
 */
export function renderApp(ui, { route = '/', pattern } = {}) {
  const content = pattern ? (
    <Routes>
      <Route path={pattern} element={ui} />
    </Routes>
  ) : (
    ui
  )
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <CartProvider>{content}</CartProvider>
      </AuthProvider>
    </MemoryRouter>
  )
}

export function renderPage(Page, opts = {}) {
  return renderApp(<Page />, opts)
}

/** Pushes the live auth context into a test-controlled array. */
export function AuthProbe({ sink }) {
  const auth = useAuth()
  useEffect(() => {
    sink?.(auth)
  })
  return null
}

/** Pushes the live cart context into a test-controlled array. */
export function CartProbe({ sink }) {
  const cart = useCart()
  useEffect(() => {
    sink?.(cart)
  })
  return null
}

/** Collects every push from a probe into an array (last = current state). */
export function makeSink() {
  const states = []
  return { states, fn: (s) => states.push(s) }
}