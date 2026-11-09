import { useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { ORDER_STATUSES } from '../lib/roles.js'
import { OrderCard } from '../components/OrderCard.jsx'
import { EmptyState, ErrorNotice, Loading, Pagination } from '../components/ui.jsx'

/**
 * Customer dashboard — "My orders" (FE-10, ORDR-01).
 * The backend scopes the list to the authenticated customer (AUTHZ-02);
 * the filters here are just the query params the endpoint documents.
 */
export default function CustomerOrders() {
  const [status, setStatus] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [applied, setApplied] = useState({ status: '', dateFrom: '', dateTo: '' })
  const [page, setPage] = useState({ limit: 20, offset: 0 })

  const { data, error, loading, reload } = useAsync(
    () =>
      get('/orders', {
        ...page,
        status: applied.status || undefined,
        date_from: applied.dateFrom || undefined,
        date_to: applied.dateTo || undefined,
      }),
    [page.offset, applied]
  )

  return (
    <section aria-labelledby="orders-h">
      <h1 id="orders-h">My orders</h1>

      <form
        className="filter-bar"
        onSubmit={(e) => {
          e.preventDefault()
          setPage((p) => ({ ...p, offset: 0 }))
          setApplied({ status, dateFrom, dateTo })
        }}
      >
        <label htmlFor="filter-status" className="filter-label">
          Status
        </label>
        <select id="filter-status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>
          {ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
        <label htmlFor="filter-from" className="filter-label">
          From
        </label>
        <input
          id="filter-from"
          type="datetime-local"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />
        <label htmlFor="filter-to" className="filter-label">
          To
        </label>
        <input id="filter-to" type="datetime-local" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        <button type="submit" className="btn">
          Filter
        </button>
      </form>

      {loading && <Loading label="Loading your orders…" />}
      {error && <ErrorNotice error={error} onRetry={reload} />}

      {!loading && !error && (
        <>
          {data.items.length === 0 ? (
            <EmptyState
              title="No orders found."
              hint={applied.status || applied.dateFrom || applied.dateTo ? 'Try different filters.' : 'Your orders will appear here.'}
            />
          ) : (
            <div className="stack">
              {data.items.map((o) => (
                <OrderCard
                  key={o.id}
                  order={o}
                  detailTo={`/orders/${o.id}`}
                  actions={
                    <Link className="btn" to={`/orders/${o.id}`}>
                      View
                    </Link>
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
