import { useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { formatDateTime, timeAgo } from '../lib/format.js'
import { EmptyState, ErrorNotice, Loading, Money, Pagination } from '../components/ui.jsx'

/**
 * Owner reminders (FE-11, T-M13-04; BG-04/D6).
 *
 * These are the stale orders the scanner (60 s / 15 min, PLACED + ACCEPTED)
 * surfaced for THIS owner's restaurant. The scanner resolves a reminder
 * automatically once the order progresses, so the list shrinks on its own;
 * "dismiss" here only hides it locally for the current visit (there is no
 * server-side acknowledge endpoint — the row's lifecycle is the scanner's).
 */
export default function OwnerReminders() {
  const [page, setPage] = useState({ limit: 50, offset: 0 })
  const [hidden, setHidden] = useState(() => new Set())

  const { data, error, loading, reload } = useAsync(
    () => get('/owner/reminders', page),
    [page.offset]
  )

  const visible = (data?.items ?? []).filter((r) => !hidden.has(r.id))

  return (
    <section aria-labelledby="reminders-h">
      <h1 id="reminders-h">Overdue orders</h1>
      <p className="muted">
        Orders that have been waiting in PLACED or ACCEPTED for more than 15 minutes. These
        resolve automatically as soon as you act on the order.
      </p>

      {loading && <Loading label="Loading reminders…" />}
      {error && <ErrorNotice error={error} onRetry={reload} />}

      {!loading && !error && (
        <>
          {visible.length === 0 ? (
            <EmptyState title="Nothing overdue." hint="New stale orders will appear here." />
          ) : (
            <div className="stack">
              {visible.map((r) => (
                <article key={r.id} className="card reminder">
                  <p>
                    <Link to={`/owner/orders/${r.order_id}`}>Order #{r.order_id}</Link>{' '}
                    <span className="muted">
                      stuck at {r.status_at_reminder.replace(/_/g, ' ')} for a while
                    </span>
                  </p>
                  <dl className="order-meta">
                    <div>
                      <dt>Detected</dt>
                      <dd>
                        {formatDateTime(r.detected_at)} <span className="muted">({timeAgo(r.detected_at)})</span>
                      </dd>
                    </div>
                    <div>
                      <dt>Total</dt>
                      <dd>
                        <Money cents={r.order_total_cents} />
                      </dd>
                    </div>
                  </dl>
                  <div className="actions-row">
                    <button
                      type="button"
                      className="btn"
                      onClick={() => setHidden((h) => new Set(h).add(r.id))}
                    >
                      Dismiss (this visit)
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
          <Pagination page={page} total={data?.total ?? 0} onPage={setPage} />
        </>
      )}
    </section>
  )
}
