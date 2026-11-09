/**
 * T-M12-10 — AI insights page: question box, loading, error states, answer
 * render. The M10 backend is the stretch milestone, so the page must
 * degrade gracefully (404/503 → "not available yet"), and a RATE_LIMITED
 * response must read as a calm message, not a crash.
 */
import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { renderPage } from '../../test/harness.jsx'
import { tokenStore } from '../../lib/api.js'
import { mockApi } from '../../test/mockApi.js'
import { userCustomer } from '../../test/factories.js'
import Insights from '../Insights.jsx'

function seedCustomer() {
  tokenStore.set('tok')
  tokenStore.setUser(userCustomer)
}

describe('Insights page (T-M12-10)', () => {
  it('renders the question box with a length counter (AI-04 bounded input)', async () => {
    seedCustomer()
    mockApi([['GET', '/auth/me', userCustomer]])
    const user = userEvent.setup()
    renderPage(Insights, { route: '/insights' })

    const box = await screen.findByLabelText(/your question/i)
    await user.type(box, 'What did I spend?')
    expect(screen.getByText(/500/)).toBeInTheDocument() // the counter shows the cap
  })

  it('sends only the question (no customer id — AI-05), and renders the answer', async () => {
    seedCustomer()
    const { calls } = mockApi([
      ['GET', '/auth/me', userCustomer],
      ['POST', '/insights/question', { answer: 'You spent €30.50 last month across two orders.' }],
    ])
    const user = userEvent.setup()
    renderPage(Insights, { route: '/insights' })

    await user.type(await screen.findByLabelText(/your question/i), 'What did I spend?')
    await user.click(screen.getByRole('button', { name: /ask/i }))

    const call = calls.find((c) => c.path === '/insights/question')
    expect(call.body).toEqual({ question: 'What did I spend?' })
    expect(call.body).not.toHaveProperty('customer_id')

    expect(await screen.findByText(/€30\.50/)).toBeInTheDocument()
  })

  it('a 404 (endpoint not implemented yet) degrades to a clear "unavailable" notice', async () => {
    seedCustomer()
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['POST', '/insights/question', { status: 404, body: { detail: 'Not found.', code: 'HTTP_ERROR' } }],
    ])
    const user = userEvent.setup()
    renderPage(Insights, { route: '/insights' })

    await user.type(await screen.findByLabelText(/your question/i), 'Hello?')
    await user.click(screen.getByRole('button', { name: /ask/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/not available in this build yet/i)
  })

  it('a 503 (feature degraded — e.g. no key configured) also degrades cleanly (T-M10-09 contract)', async () => {
    seedCustomer()
    mockApi([
      ['GET', '/auth/me', userCustomer],
      [
        'POST',
        '/insights/question',
        { status: 503, body: { detail: 'Insights are temporarily unavailable.', code: 'FEATURE_DISABLED' } },
      ],
    ])
    const user = userEvent.setup()
    renderPage(Insights, { route: '/insights' })

    await user.type(await screen.findByLabelText(/your question/i), 'Hello?')
    await user.click(screen.getByRole('button', { name: /ask/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/not available in this build yet/i)
  })

  it('a rate-limit response reads as a calm "slow down" message (AI-07)', async () => {
    seedCustomer()
    mockApi([
      ['GET', '/auth/me', userCustomer],
      [
        'POST',
        '/insights/question',
        { status: 429, body: { detail: 'Too many requests.', code: 'RATE_LIMITED' } },
      ],
    ])
    const user = userEvent.setup()
    renderPage(Insights, { route: '/insights' })

    await user.type(await screen.findByLabelText(/your question/i), 'Again?')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/asking too quickly/i)
  })

  it('disables the button while "thinking"', async () => {
    seedCustomer()
    let settle
    const pending = () =>
      new Promise((resolve, reject) => {
        settle = { resolve, reject }
      })
    mockApi([
      ['GET', '/auth/me', userCustomer],
      ['POST', '/insights/question', () => pending()],
    ])
    const user = userEvent.setup()
    renderPage(Insights, { route: '/insights' })

    await user.type(await screen.findByLabelText(/your question/i), 'Hello?')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    expect(screen.getByRole('button', { name: /thinking/i })).toBeDisabled()
    settle.resolve({ answer: 'Hello to you too!' })
    await screen.findByText('Hello to you too!')
  })
})
