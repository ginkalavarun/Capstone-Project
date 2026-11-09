import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { get } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { useCart } from '../context/CartContext.jsx'
import { EmptyState, ErrorNotice, Loading, Money, Pagination } from '../components/ui.jsx'

/**
 * Restaurant menu (FE-07, MENU-01…06). Public (D16).
 *
 * Filters are server-side (contract §4): dish-name substring search and
 * inclusive min/max price. Prices are entered in euros by humans and sent
 * as integer cents (D3). Dishes with `available: false` are shown greyed
 * and cannot be added to the cart (MENU-07 — the backend re-checks at
 * checkout).
 */
export default function Menu() {
  const { id } = useParams()
  const { addItem, cart } = useCart()

  const [search, setSearch] = useState('')
  const [minPrice, setMinPrice] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const [applied, setApplied] = useState({ search: '', min: '', max: '' })
  const [page, setPage] = useState({ limit: 20, offset: 0 })
  const [swapPrompt, setSwapPrompt] = useState(null) // dish awaiting cart replacement
  const [flash, setFlash] = useState(null)

  const restaurant = useAsync(() => get(`/restaurants/${id}`), [id])
  const menu = useAsync(
    () =>
      get(`/restaurants/${id}/menu`, {
        ...page,
        search: applied.search || undefined,
        min_price_cents: applied.min ? Math.round(Number(applied.min) * 100) : undefined,
        max_price_cents: applied.max ? Math.round(Number(applied.max) * 100) : undefined,
      }),
    [id, page.offset, applied]
  )

  const onAdd = (dish) => {
    const result = addItem(dish, restaurant.data)
    if (result === 'replacement-needed') {
      setSwapPrompt(dish)
      setFlash(null)
      return
    }
    setFlash(`Added ${dish.name} to your cart.`)
  }

  const confirmSwap = () => {
    addItem(swapPrompt, restaurant.data, { force: true })
    setFlash(`Cart replaced: now from ${restaurant.data.name}.`)
    setSwapPrompt(null)
  }

  return (
    <section aria-labelledby="menu-h">
      {restaurant.loading && <Loading label="Loading restaurant…" />}
      {restaurant.error && <ErrorNotice error={restaurant.error} onRetry={restaurant.reload} />}

      {restaurant.data && (
        <>
          <p>
            <Link to="/restaurants">← All restaurants</Link>
          </p>
          <h1 id="menu-h">{restaurant.data.name}</h1>
          {restaurant.data.description && <p className="muted">{restaurant.data.description}</p>}
          <p>
            Delivery fee: <Money cents={restaurant.data.delivery_fee_cents} />
          </p>

          <form
            className="filter-bar"
            onSubmit={(e) => {
              e.preventDefault()
              setPage((p) => ({ ...p, offset: 0 }))
              // `applied` is read as {search, min, max} by the fetch — map the
              // input state (minPrice/maxPrice) onto those key names.
              setApplied({ search, min: minPrice, max: maxPrice })
            }}
          >
            <label htmlFor="dish-search" className="filter-label">
              Dish
            </label>
            <input
              id="dish-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="search by name"
            />
            <label htmlFor="price-min" className="filter-label">
              Min €
            </label>
            <input
              id="price-min"
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={minPrice}
              onChange={(e) => setMinPrice(e.target.value)}
            />
            <label htmlFor="price-max" className="filter-label">
              Max €
            </label>
            <input
              id="price-max"
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value)}
            />
            <button type="submit" className="btn">
              Filter
            </button>
          </form>

          {flash && (
            <p role="status" className="notice notice-info">
              {flash}
            </p>
          )}

          {swapPrompt && (
            <div role="alert" className="notice notice-info">
              <p>
                Your cart holds dishes from <strong>{cart.restaurant?.name}</strong>. Add “
                {swapPrompt.name}” from {restaurant.data.name} instead?
              </p>
              <button type="button" className="btn btn-primary" onClick={confirmSwap}>
                Replace cart
              </button>{' '}
              <button type="button" className="btn" onClick={() => setSwapPrompt(null)}>
                Cancel
              </button>
            </div>
          )}

          {menu.loading && <Loading label="Loading menu…" />}
          {menu.error && <ErrorNotice error={menu.error} onRetry={menu.reload} />}

          {!menu.loading && !menu.error && (
            <>
              {menu.data.items.length === 0 ? (
                <EmptyState title="No dishes match your filters." hint="Try widening the price range." />
              ) : (
                <div className="card-grid">
                  {menu.data.items.map((dish) => (
                    <article key={dish.id} className={`card dish ${dish.available ? '' : 'dish-unavailable'}`}>
                      <h2>{dish.name}</h2>
                      {dish.description && <p className="muted">{dish.description}</p>}
                      <p className="dish-price">
                        <Money cents={dish.price_cents} />
                      </p>
                      {dish.available ? (
                        <button type="button" className="btn" onClick={() => onAdd(dish)}>
                          Add to cart
                        </button>
                      ) : (
                        <span className="muted" aria-disabled="true">
                          Not available
                        </span>
                      )}
                    </article>
                  ))}
                </div>
              )}
              <Pagination page={page} total={menu.data.total} onPage={setPage} />
            </>
          )}
        </>
      )}
    </section>
  )
}
