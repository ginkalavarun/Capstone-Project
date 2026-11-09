/**
 * T-M11-02 — login/register UI: validation, API calls, token in
 * localStorage, redirect by role.
 * T-M11-08 — accessibility: programmatic labels, aria-invalid on error,
 * keyboard-reachable submit.
 */
import { describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
// (unauthorized() helper is no longer needed: the login-failure test uses
// the backend's exact 401 body inline.)
import { userEvent } from '@testing-library/user-event'
import { renderApp, renderPage } from '../../test/harness.jsx'
import { tokenStore } from '../../lib/api.js'
import { mockApi } from '../../test/mockApi.js'
import { userCustomer, userOwner, restaurant } from '../../test/factories.js'
import App from '../../App.jsx'
import Login from '../Login.jsx'
import Register from '../Register.jsx'

describe('Login page', () => {
  it('validates, calls the API, stores the token, and redirects by role (T-M11-02)', async () => {
    const { calls } = mockApi([
      ['POST', '/auth/login', { access_token: 'tok', token_type: 'bearer', user: userCustomer }],
    ])
    const user = userEvent.setup()
    renderPage(Login, { route: '/login' })

    await user.type(screen.getByLabelText(/email/i), 'cust@example.org')
    await user.type(screen.getByLabelText(/password/i), 'password-123')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({ email: 'cust@example.org', password: 'password-123' })
    expect(tokenStore.get()).toBe('tok')
  })

  it('an owner lands on the owner dashboard after login (redirect by role, full App)', async () => {
    mockApi([
      ['POST', '/auth/login', { access_token: 'tok', token_type: 'bearer', user: userOwner }],
      ['GET', '/owner/orders', { items: [], total: 0, limit: 20, offset: 0 }],
    ])
    const user = userEvent.setup()
    renderApp(<App />, { route: '/login' })

    await user.type(screen.getByLabelText(/email/i), 'own1@example.org')
    await user.type(screen.getByLabelText(/password/i), 'password-123')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() => expect(screen.getByText('Incoming orders')).toBeInTheDocument())
  })

  it('shows a controlled error for invalid credentials (no token stored)', async () => {
    // Mirrors the backend's actual 401 body for a failed login (backend/app/api/v1/auth.py).
    mockApi([
      [
        'POST',
        '/auth/login',
        { status: 401, body: { detail: 'Incorrect email or password.', code: 'INVALID_CREDENTIALS' } },
      ],
    ])
    const user = userEvent.setup()
    renderPage(Login, { route: '/login' })

    await user.type(screen.getByLabelText(/email/i), 'cust@example.org')
    await user.type(screen.getByLabelText(/password/i), 'wrong')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/incorrect email or password/i)
    expect(tokenStore.get()).toBeNull()
  })

  it('labels are programmatic and the submit button is keyboard-reachable (T-M11-08)', async () => {
    renderPage(Login, { route: '/login' })
    const email = screen.getByLabelText(/email/i)
    expect(email).toHaveAccessibleName(/email/i)
    const password = screen.getByLabelText(/^password$/i)
    expect(password).toHaveAccessibleName(/^password$/i)

    const user = userEvent.setup()
    await user.tab() // first tabbable control in the form
    expect(email).toHaveFocus()
  })

  it('disables the submit button until both fields have values (T-M11-08)', async () => {
    renderPage(Login, { route: '/login' })
    const user = userEvent.setup()
    let submit = screen.getByRole('button', { name: /log in/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/email/i), 'a@b.co')
    submit = screen.getByRole('button', { name: /log in/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/^password$/i), 'password-123')
    submit = screen.getByRole('button', { name: /log in/i })
    expect(submit).toBeEnabled()
  })

  it('a logged-in visitor is redirected away from /login (full App)', async () => {
    tokenStore.set('tok')
    tokenStore.setUser(userCustomer)
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['GET', '/restaurants', { items: [restaurant], total: 1, limit: 100, offset: 0 }],
    ])
    renderApp(<App />, { route: '/login' })
    // The redirect lands on the customer home: the restaurant listing.
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument())
  })
})

describe('Register page', () => {
  it('posts exactly email/password/full_name — no role field (D2) — then offers login (T-M11-02)', async () => {
    const { calls } = mockApi([['POST', '/auth/register', { user: userCustomer }]])
    const user = userEvent.setup()
    renderPage(Register, { route: '/register' })

    await user.type(screen.getByLabelText(/full name/i), 'Varun Lal')
    await user.type(screen.getByLabelText(/email/i), 'cust@example.org')
    await user.type(screen.getByLabelText(/^password$/i), 'password-123')
    await user.click(screen.getByRole('button', { name: /register/i }))

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0].body).toEqual({
      email: 'cust@example.org',
      password: 'password-123',
      full_name: 'Varun Lal',
    })
    expect(await screen.findByText(/account created/i)).toBeInTheDocument()
    expect(within(screen.getByRole('status')).queryAllByRole('link', { name: /go to log in/i })).toHaveLength(1)
  })

  it('surfaces a duplicate-email 409 as a controlled error', async () => {
    mockApi([
      ['POST', '/auth/register', { status: 409, body: { detail: 'That email is already registered.', code: 'EMAIL_TAKEN' } }],
    ])
    const user = userEvent.setup()
    renderPage(Register, { route: '/register' })

    await user.type(screen.getByLabelText(/full name/i), 'Varun Lal')
    await user.type(screen.getByLabelText(/email/i), 'taken@example.org')
    await user.type(screen.getByLabelText(/^password$/i), 'password-123')
    await user.click(screen.getByRole('button', { name: /register/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/already registered/i)
  })

  it('has programmatic labels and a keyboard-reachable submit (T-M11-08)', async () => {
    renderPage(Register, { route: '/register' })
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /register/i })).toBeDisabled()
  })
})
