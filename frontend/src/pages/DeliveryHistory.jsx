import { useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { OrderCard } from '../components/OrderCard.jsx'
import { EmptyState, ErrorNotice, Loading, Pagination } from '../components/ui.jsx'

/**
 * Delivery history (FE-12, T-M13-08, DELV-03): the caller's past completed
 * assignments (DELIVERED — including ones later refunded). No actions; the
 * detail page is read-only context for the partner.
 */
export default function DeliveryHistory() {
  const [page, setPage] = useState({ limit: 20, offset: 0 })

  const { data, error, loading, reload } = useAsync(
    () => get('/delivery/history', page),
    [page.offset]
  )

  return (
    <section aria-labelledby="history-h">
      <h1 id="history-h">Delivery history</h1>

      {loading && <Loading label="Loading history…" />}
      {error && <ErrorNotice error={error} onRetry={reload} />}

      {!loading && !error && (
        <>
          {data.items.length === 0 ? (
            <EmptyState title="No completed deliveries yet." />
          ) : (
            <div className="stack">
              {data.items.map((o) => (
                <OrderCard
                  key={o.id}
                  order={o}
                  detailTo={`/delivery/orders/${o.id}`}
                  actions={
                    <Link className="btn" to={`/delivery/orders/${o.id}`}>
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
