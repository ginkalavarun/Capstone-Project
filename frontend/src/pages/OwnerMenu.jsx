import { useEffect, useState } from 'react'
import { del, get, post, put } from '../lib/api.js'
import { useAsync } from '../hooks/useAsync.js'
import { ErrorNotice, Loading, Money } from '../components/ui.jsx'

/**
 * Owner menu management (FE-11, T-M13-05).
 *
 * The page first fetches the owner's own restaurant (`GET /owner/restaurant`
 * — batch 8), then manages dishes on it:
 *   - create dish        POST /restaurants/{id}/menu
 *   - edit dish          PUT /menu-items/{id}  (partial update)
 *   - soft-remove        DELETE /menu-items/{id}  → available=false (D32)
 *   - re-enable          PUT /menu-items/{id} {available: true}
 *
 * Dishes are deactivated, never hard-deleted: historical order snapshots
 * keep working (D3). Prices are entered in euros, sent as integer cents.
 */
function DishForm({ dish, onSaved, onCancel, submitLabel = 'Save' }) {
  const [name, setName] = useState(dish?.name ?? '')
  const [description, setDescription] = useState(dish?.description ?? '')
  const [price, setPrice] = useState(dish ? (dish.price_cents / 100).toFixed(2) : '')
  const [available, setAvailable] = useState(dish?.available ?? true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    const body = {
      name: name.trim(),
      description: description.trim() || null,
      price_cents: Math.round(Number(price) * 100),
      available,
    }
    try {
      await onSaved(body)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const fid = dish?.id ?? 'new'
  return (
    <form className="form dish-form" onSubmit={submit} aria-busy={busy}>
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}
      <label htmlFor={`name-${fid}`}>Name</label>
      <input
        id={`name-${fid}`}
        required
        minLength={1}
        maxLength={120}
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <label htmlFor={`desc-${fid}`}>Description</label>
      <input
        id={`desc-${fid}`}
        maxLength={1000}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <label htmlFor={`price-${fid}`}>Price (€)</label>
      <input
        id={`price-${fid}`}
        type="number"
        min="0"
        step="0.01"
        inputMode="decimal"
        required
        value={price}
        onChange={(e) => setPrice(e.target.value)}
      />
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={available}
          onChange={(e) => setAvailable(e.target.checked)}
        />{' '}
        Available
      </label>
      <div className="actions-row">
        <button type="submit" className="btn btn-primary" disabled={busy || !name.trim() || !price}>
          {busy ? 'Saving…' : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}

export default function OwnerMenu() {
  const { data: rest, error: restError, loading: restLoading, reload } = useAsync(
    () => get('/owner/restaurant'),
    []
  )
  const [menu, setMenu] = useState(null) // full list, client-managed after saves
  const [menuError, setMenuError] = useState(null)
  const [loadingMenu, setLoadingMenu] = useState(false)
  const [editing, setEditing] = useState(null) // dish being edited
  const [createNonce, setCreateNonce] = useState(0) // remounts the add-form after a save

  const loadMenu = async () => {
    if (!rest) return
    setMenuError(null)
    setLoadingMenu(true)
    try {
      const page = await get(`/restaurants/${rest.id}/menu`, { limit: 100, offset: 0 })
      setMenu(page.items)
    } catch (err) {
      setMenuError(err.message)
    } finally {
      setLoadingMenu(false)
    }
  }

  // Load once the restaurant is known.
  useEffect(() => {
    if (rest) loadMenu()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rest?.id])

  if (restLoading) return <Loading label="Loading your restaurant…" />
  if (restError)
    return (
      <div className="card">
        <ErrorNotice error={restError} onRetry={reload} />
        <p className="muted">Menu management needs a provisioned restaurant.</p>
      </div>
    )

  return (
    <section className="card" aria-labelledby="menu-mgmt-h">
      <h1 id="menu-mgmt-h">
        Menu <span className="muted">— {rest.name}</span>
      </h1>

      <div className="section">
        <h2>Add a dish</h2>
        <DishForm
          key={`create-${createNonce}`}
          dish={null}
          submitLabel="Add dish"
          onSaved={async (body) => {
            await post(`/restaurants/${rest.id}/menu`, body)
            setCreateNonce((n) => n + 1)
            setEditing(null)
            await loadMenu()
          }}
        />
      </div>

      {menuError && (
        <div className="notice notice-error" role="alert">
          {menuError}
        </div>
      )}

      <div className="section">
        <h2>Dishes</h2>
        {menu === null && loadingMenu ? (
          <Loading label="Loading menu…" />
        ) : menu === null ? (
          <p className="muted">Menu could not be loaded.</p>
        ) : menu.length === 0 ? (
          <p className="muted">No dishes yet — add your first one above.</p>
        ) : (
          <div className="stack">
            {menu.map((dish) =>
              editing?.id === dish.id ? (
                <article key={dish.id} className="card inner">
                  <DishForm
                    key={dish.id}
                    dish={dish}
                    onSaved={async (body) => {
                      await put(`/menu-items/${dish.id}`, body)
                      setEditing(null)
                      await loadMenu()
                    }}
                    onCancel={() => setEditing(null)}
                  />
                </article>
              ) : (
                <article key={dish.id} className={`card inner ${dish.available ? '' : 'disabled'}`}>
                  <h3>
                    {dish.name} <span className="muted">· <Money cents={dish.price_cents} /></span>
                  </h3>
                  {dish.description && <p className="muted">{dish.description}</p>}
                  <p>{dish.available ? 'Available' : 'Not available'}</p>
                  <div className="actions-row">
                    <button type="button" className="btn" onClick={() => setEditing(dish)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className={dish.available ? 'btn btn-danger' : 'btn'}
                      onClick={async () => {
                        try {
                          if (dish.available) await del(`/menu-items/${dish.id}`)
                          else await put(`/menu-items/${dish.id}`, { available: true })
                          await loadMenu()
                        } catch (err) {
                          setMenuError(err.message)
                        }
                      }}
                    >
                      {dish.available ? 'Mark unavailable' : 'Re-enable'}
                    </button>
                  </div>
                </article>
              )
            )}
          </div>
        )}
      </div>
    </section>
  )
}
