import { useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { EmptyState, ErrorNotice, Loading, Money, Pagination } from '../components/ui.jsx'

/**
 * Restaurant listing (FE-06). Public — the catalog needs no login (D16).
 * The backend endpoint has no search parameter, so the text box filters
 * the loaded page client-side (the campus list is small; `limit=100` keeps
 * it on one page). Pagination is hidden while filtering.
 */
export default function Restaurants() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState({ limit: 100, offset: 0 })

  const { data, error, loading, reload } = useAsync(
    () => get('/restaurants', page),
    [page.offset]
  )

  const all = data?.items ?? []
  const items = search
    ? all.filter((r) => r.name.toLowerCase().includes(search.toLowerCase()))
    : all

  return (
    <section aria-labelledby="restaurants-h">
      <h1 id="restaurants-h">Restaurants</h1>

      <form
        className="filter-bar"
        onSubmit={(e) => {
          e.preventDefault()
          setPage((p) => ({ ...p, offset: 0 }))
        }}
      >
        <label htmlFor="rest-search" className="filter-label">
          Search by name
        </label>
        <input
          id="rest-search"
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="e.g. Alpha"
        />
        <button type="submit" className="btn">
          Search
        </button>
      </form>

      {loading && <Loading label="Loading restaurants…" />}
      {error && <ErrorNotice error={error} onRetry={reload} />}

      {!loading && !error && (
        <>
          {items.length === 0 ? (
            <EmptyState
              title={search ? 'No restaurants match your search.' : 'No restaurants yet.'}
              hint={search ? 'Try a different name.' : 'Check back later.'}
            />
          ) : (
            <div className="card-grid">
              {items.map((r) => (
                <article key={r.id} className="card">
                  <h2>
                    <Link to={`/restaurants/${r.id}`}>{r.name}</Link>
                  </h2>
                  {r.description && <p>{r.description}</p>}
                  <p className="muted">{r.address}</p>
                  <p>
                    Delivery fee: <Money cents={r.delivery_fee_cents} />
                  </p>
                  <Link className="btn" to={`/restaurants/${r.id}`}>
                    View menu
                  </Link>
                </article>
              ))}
            </div>
          )}
          {!search && <Pagination page={page} total={data.total} onPage={setPage} />}
        </>
      )}
    </section>
  )
}
