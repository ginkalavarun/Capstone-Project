/**
 * Client-generated idempotency keys for checkout (D34): 1–64 chars,
 * scoped to the authenticated customer by the backend. A failed (network)
 * retry reuses the SAME key + payload and the server returns the original
 * order (200); a changed payload with the same key is a 409
 * IDEMPOTENCY_MISMATCH, after which the checkout UI mints a fresh key.
 */
export function newIdempotencyKey() {
  try {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  } catch {
    /* fall through to the manual fallback */
  }
  return `key-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`
}
