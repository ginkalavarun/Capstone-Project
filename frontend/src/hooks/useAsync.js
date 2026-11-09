import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Tiny data-fetching hook behind every async view (FE-14, T-M11-06):
 * uniform `loading` / `error` / `data` / `reload` so all pages render the
 * same three states. The `fn` closure is kept in a ref so dependencies can
 * be explicit (page params) instead of the whole callback identity.
 */
export function useAsync(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fnRef
      .current()
      .then((d) => {
        if (!cancelled) {
          setData(d)
          setLoading(false)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setData(null)
          setError(e)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, error, loading, reload }
}
