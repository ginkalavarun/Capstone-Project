import { useState } from 'react'
import { post, ApiError } from '../lib/api.js'
import { money } from '../lib/format.js'

const MAX_QUESTION = 500

/**
 * AI order insights (FE-10 / M10, AI-01…07, D9).
 *
 * `POST /insights/question` is backend-only: the OpenAI key never reaches
 * the browser (D9/AI-09), the model context is the authenticated customer's
 * own orders only (AI-02), and the question is length-bounded (AI-04).
 *
 * Graceful degradation (D9): without a server-side OpenAI key the API still
 * returns 200 with `provider: "unconfigured"` and `answer: null` — we show
 * a clear configuration notice plus the exact app-computed stats (the model
 * is never faked). A 503/404 from a *different* backend build falls back to
 * the same "not available" state.
 */
export default function Insights() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null) // InsightOut on success
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const ask = async (e) => {
    e.preventDefault()
    setError(null)
    setResult(null)
    setBusy(true)
    try {
      const res = await post('/insights/question', { question: question.trim() })
      setResult(res)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'RATE_LIMITED') {
        setError('You are asking too quickly — please wait a minute before asking again.')
      } else if (err instanceof ApiError && err.code === 'AI_UPSTREAM_RATE_LIMITED') {
        setError('The AI provider is busy right now — please try again shortly.')
      } else if (err instanceof ApiError && (err.status === 404 || err.status === 503)) {
        setError(
          'AI insights are not available in this build yet. Your orders are still fully visible in “My orders”.'
        )
      } else {
        setError(err.message)
      }
    } finally {
      setBusy(false)
    }
  }

  const stats = result?.stats

  return (
    <section className="card" aria-labelledby="insights-h">
      <h1 id="insights-h">Insights about my orders</h1>
      <p className="muted">
        Ask a question about your own order history (totals, favourites, timing). Only your data
        is used.
      </p>

      {result && result.answer && (
        <div className="section">
          <h2>Answer</h2>
          <p className="insight-answer">{result.answer}</p>
        </div>
      )}

      {result && !result.answer && (
        <div className="notice notice-info" role="status">
          {result.provider === 'unconfigured'
            ? 'AI answers are not configured on this server yet (OPENAI_API_KEY). The exact figures below are computed by the app, not by the model.'
            : 'Your order history is not set up yet — place your first order to see insights.'}
        </div>
      )}

      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}

      {stats && (
        <div className="section">
          <h2>Your numbers (exact, from your orders)</h2>
          <dl className="order-meta">
            <div>
              <dt>Orders</dt>
              <dd>{stats.order_count}</dd>
            </div>
            <div>
              <dt>Gross paid</dt>
              <dd>{money(stats.gross_cents)}</dd>
            </div>
            <div>
              <dt>Refunded</dt>
              <dd>{money(stats.refunded_cents)}</dd>
            </div>
            <div>
              <dt>Net retained</dt>
              <dd>{money(stats.net_retained_cents)}</dd>
            </div>
            <div>
              <dt>Average order</dt>
              <dd>{money(stats.avg_order_cents)}</dd>
            </div>
            <div>
              <dt>Delivered</dt>
              <dd>{stats.delivered_count}</dd>
            </div>
            {stats.top_restaurants?.length > 0 && (
              <div>
                <dt>Favourite spots</dt>
                <dd>{stats.top_restaurants.join(', ')}</dd>
              </div>
            )}
            {stats.top_dishes?.length > 0 && (
              <div>
                <dt>Favourite dishes</dt>
                <dd>{stats.top_dishes.join(', ')}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      <form className="form" onSubmit={ask}>
        <label htmlFor="insight-question">Your question</label>
        <textarea
          id="insight-question"
          required
          minLength={1}
          maxLength={MAX_QUESTION}
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. What did I spend last month?"
        />
        <p className="muted field-hint">
          {question.length}/{MAX_QUESTION}
        </p>
        <button type="submit" className="btn btn-primary" disabled={busy || !question.trim()}>
          {busy ? 'Thinking…' : 'Ask'}
        </button>
      </form>
    </section>
  )
}
