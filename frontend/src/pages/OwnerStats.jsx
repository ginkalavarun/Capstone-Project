import { useState } from 'react'
import { get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { ErrorNotice, Loading, Money } from '../components/ui.jsx'

/**
 * Owner statistics (FE-11, T-M13-05; DASH-02, D35).
 *
 * All money is integer euro cents (D3/D26). The metric names are the
 * documented D35 set — deliberately NOT all called "revenue":
 *   gross = Σ totals of orders placed in the range (every placement pays)
 *   refunded = Σ refunded ledger events (cancellation reversals +
 *              approved refunds) in the range
 *   net retained = gross − refunded, exactly
 *   delivered count includes orders that were later refunded (D31).
 */
export default function OwnerStats() {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [applied, setApplied] = useState({ from: '', to: '' })

  const { data, error, loading, reload } = useAsync(
    () =>
      get('/owner/stats', {
        date_from: applied.from || undefined,
        date_to: applied.to || undefined,
      }),
    [applied]
  )

  return (
    <section className="card" aria-labelledby="stats-h">
      <h1 id="stats-h">Statistics</h1>

      <form
        className="filter-bar"
        onSubmit={(e) => {
          e.preventDefault()
          setApplied({ from: dateFrom, to: dateTo })
        }}
      >
        <label htmlFor="s-from" className="filter-label">
          From
        </label>
        <input
          id="s-from"
          type="datetime-local"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />
        <label htmlFor="s-to" className="filter-label">
          To
        </label>
        <input id="s-to" type="datetime-local" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        <button type="submit" className="btn">
          Apply range
        </button>
      </form>

      {loading && <Loading label="Calculating…" />}
      {error && <ErrorNotice error={error} onRetry={reload} />}

      {data && (
        <>
          <dl className="stat-grid">
            <div>
              <dt>Orders placed</dt>
              <dd>{data.placed_order_count}</dd>
            </div>
            <div>
              <dt>Gross (mock-paid)</dt>
              <dd>
                <Money cents={data.gross_mock_paid_cents} />
              </dd>
            </div>
            <div>
              <dt>Refunded</dt>
              <dd>
                <Money cents={data.refunded_cents} />
              </dd>
            </div>
            <div>
              <dt>Net retained</dt>
              <dd>
                <Money cents={data.net_retained_cents} />
              </dd>
            </div>
            <div>
              <dt>Delivered</dt>
              <dd>{data.delivered_count}</dd>
            </div>
            <div>
              <dt>Items sold</dt>
              <dd>{data.items_sold}</dd>
            </div>
            <div>
              <dt>Average order value</dt>
              <dd>
                <Money cents={data.avg_order_value_cents} />
              </dd>
            </div>
          </dl>

          <h2>Orders by status</h2>
          <dl className="stat-grid">
            {Object.entries(data.orders_by_status).map(([status, count]) => (
              <div key={status}>
                <dt>{status.replace(/_/g, ' ')}</dt>
                <dd>{count}</dd>
              </div>
            ))}
          </dl>

          <p className="muted">
            “Gross” is the mock-paid value of orders placed in the range (this is a mock payment
            system, not real revenue); “net retained” subtracts every refund and cancellation
            reversal in the range.
          </p>
        </>
      )}
    </section>
  )
}
