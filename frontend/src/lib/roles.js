/**
 * Domain constants (mirror backend/app/core/constants.py — keep in sync).
 */
export const ROLES = {
  CUSTOMER: 'customer',
  OWNER: 'restaurant_owner',
  PARTNER: 'delivery_partner',
}

export const ORDER_STATUSES = [
  'PLACED',
  'ACCEPTED',
  'PREPARING',
  'READY',
  'ASSIGNED',
  'OUT_FOR_DELIVERY',
  'DELIVERED',
  'CANCELLED',
  'REFUNDED',
]

/** The customer-visible lifecycle, in order, for the status timeline. */
export const DELIVERY_FLOW = [
  'PLACED',
  'ACCEPTED',
  'PREPARING',
  'READY',
  'ASSIGNED',
  'OUT_FOR_DELIVERY',
  'DELIVERED',
]

export function homeFor(role) {
  if (role === ROLES.OWNER) return '/owner/orders'
  if (role === ROLES.PARTNER) return '/delivery'
  return '/restaurants'
}
