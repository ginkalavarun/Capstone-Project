import { useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { OrderCard } from '../components/OrderCard.jsx'
import { ORDER_STATUSES } from '../lib/roles.js'
import { EmptyState, ErrorNotice, Loading, Pagination } from '../components/ui.jsx'

/**
 * Delivery dashboard — active workload (FE-12, T-M13-06, DELV-01).
 * The backend returns only orders ASSIGNED to the caller that are not yet
 * DELIVERED/REFUNDED; partners who are not the assignee cannot even see
 * the order (404, AUTHZ-06).
 */
export default function DeliveryActive() {
  const [status, setStatus] = useState('')
  const [applied, setApplied] = useState('')
  const [page, setPage] = useState({ limit: 20, offset: 0 })

  const { data, error, loading, reload } = useAsync(
    () => get('/delivery/orders', { ...page, status: applied || undefined }),
    [page.offset, applied]
  )

  return (
    <section aria-labelledby="delivery-h">
      <h1 id="delivery-h">My deliveries</h1>

      <form
        className="filter-bar"
        onSubmit={(e) => {
          e.preventDefault()
          setPage((p) => ({ ...p, offset: 0 }))
          setApplied(status)
        }}
      >
        <label htmlFor="d-status" className="filter-label">
          Status
        </label>
        <select id="d-status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All active</option>
          {ORDER_STATUSES.filter((s) => !['DELIVERED', 'REFUNDED', 'CANCELLED'].includes(s)).map(
            (s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, ' ')}
              </option>
            )
          )}
        </select>
        <button type="submit" className="btn">
          Filter
        </button>
      </form>

      {loading && <Loading label="Loading deliveries…" />}
      {error && <ErrorNotice error={error} onRetry={reload} />}

      {!loading && !error && (
        <>
          {data.items.length === 0 ? (
            <EmptyState
              title="No active deliveries."
              hint="Orders assigned to you will appear here."
            />
          ) : (
            <div className="stack">
              {data.items.map((o) => (
                <OrderCard
                  key={o.id}
                  order={o}
                  detailTo={`/delivery/orders/${o.id}`}
                  actions={
                    <span className="order-actions-inline">
                      <Link className="btn" to={`/delivery/orders/${o.id}`}>
                        Open
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
