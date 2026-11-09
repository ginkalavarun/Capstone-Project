import { useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { ORDER_STATUSES } from '../lib/roles.js'
import { OrderCard } from '../components/OrderCard.jsx'
import { EmptyState, ErrorNotice, Loading, Pagination } from '../components/ui.jsx'

/**
 * Owner dashboard — incoming orders (FE-11, DASH-01).
 * The backend returns only the caller's own restaurant's orders (D24: one
 * restaurant per owner; no restaurant id is ever accepted).
 */
export default function OwnerOrders() {
  const [status, setStatus] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [applied, setApplied] = useState({ status: '', dateFrom: '', dateTo: '' })
  const [page, setPage] = useState({ limit: 20, offset: 0 })

  const { data, error, loading, reload } = useAsync(
    () =>
      get('/owner/orders', {
        ...page,
        status: applied.status || undefined,
        date_from: applied.dateFrom || undefined,
        date_to: applied.dateTo || undefined,
      }),
    [page.offset, applied]
  )

  return (
    <section aria-labelledby="owner-orders-h">
      <h1 id="owner-orders-h">Incoming orders</h1>

      <form
        className="filter-bar"
        onSubmit={(e) => {
          e.preventDefault()
          setPage((p) => ({ ...p, offset: 0 }))
          setApplied({ status, dateFrom, dateTo })
        }}
      >
        <label htmlFor="o-status" className="filter-label">
          Status
        </label>
        <select id="o-status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>
          {ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
        <label htmlFor="o-from" className="filter-label">
          From
        </label>
        <input id="o-from" type="datetime-local" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        <label htmlFor="o-to" className="filter-label">
          To
        </label>
        <input id="o-to" type="datetime-local" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        <button type="submit" className="btn">
          Filter
        </button>
      </form>

      {loading && <Loading label="Loading orders…" />}
      {error && <ErrorNotice error={error} onRetry={reload} />}

      {!loading && !error && (
        <>
          {data.items.length === 0 ? (
            <EmptyState title="No orders yet." hint="New orders will appear here as customers place them." />
          ) : (
            <div className="stack">
              {data.items.map((o) => (
                <OrderCard
                  key={o.id}
                  order={o}
                  detailTo={`/owner/orders/${o.id}`}
                  actions={
                    <span className="order-actions-inline">
                      <Link className="btn" to={`/owner/orders/${o.id}`}>
                        Manage
                      </Link>
                    </span>
                  }
                />
              ))}
            </div>
          )}
          <Pagination page={page} total={data.total} onPage={setPage} />
        </>
      )}
    </section>
  )
}
