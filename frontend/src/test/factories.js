/**
 * Canonical sample data for frontend tests — mirrors the API contract
 * shapes (docs/api-contract.md): integer cents, ISO-8601 timestamps, the
 * Page envelope.
 */
export const userCustomer = {
  id: 1,
  email: 'cust@example.org',
  full_name: 'Cust One',
  role: 'customer',
  is_active: true,
}

export const userOwner = {
  id: 2,
  email: 'own1@example.org',
  full_name: 'Owner One',
  role: 'restaurant_owner',
  is_active: true,
}

export const userPartner = {
  id: 3,
  email: 'dp1@example.org',
  full_name: 'Partner One',
  role: 'delivery_partner',
  is_active: true,
}

export const restaurant = {
  id: 1,
  name: 'Alpha',
  description: 'Campus burgers and fries.',
  address: 'Student Quad 1',
  delivery_fee_cents: 250,
  created_at: '2026-11-01T09:00:00+00:00',
  updated_at: '2026-11-01T09:00:00+00:00',
}

export const restaurantTwo = {
  id: 2,
  name: 'Beta',
  description: 'Rolls and tea.',
  address: 'Library Annex',
  delivery_fee_cents: 350,
  created_at: '2026-11-01T09:00:00+00:00',
  updated_at: '2026-11-01T09:00:00+00:00',
}

export const dish = {
  id: 10,
  restaurant_id: 1,
  name: 'Grilled Chicken',
  description: 'Marinated, grilled to order.',
  price_cents: 1200,
  available: true,
  created_at: '2026-11-01T10:00:00+00:00',
  updated_at: '2026-11-01T10:00:00+00:00',
}

export const dishUnavailable = {
  id: 11,
  restaurant_id: 1,
  name: 'Fries',
  description: null,
  price_cents: 400,
  available: false,
  created_at: '2026-11-01T10:00:00+00:00',
  updated_at: '2026-11-01T10:30:00+00:00',
}

export function order(overrides = {}) {
  return {
    id: 100,
    status: 'PLACED',
    payment_status: 'mock_paid',
    refund_status: null,
    refund_reason: null,
    status_updated_at: '2026-11-07T18:00:00+00:00',
    delivered_at: null,
    restaurant_id: 1,
    restaurant_name: 'Alpha',
    customer_id: 1,
    customer_name: 'Cust One',
    delivery_partner_id: null,
    delivery_address: 'Dorm 4, room 12',
    items_subtotal_cents: 2400,
    delivery_fee_cents: 250,
    total_cents: 2650,
    items: [
      {
        id: 1,
        menu_item_id: 10,
        item_name: 'Grilled Chicken',
        unit_price_cents: 1200,
        quantity: 2,
        line_total_cents: 2400,
      },
    ],
    created_at: '2026-11-07T18:00:00+00:00',
    ...overrides,
  }
}

export const page = (items, total = items.length) => ({ items, total, limit: 20, offset: 0 })

export const reminder = {
  id: 5,
  order_id: 100,
  status_at_reminder: 'PLACED',
  detected_at: '2026-11-07T18:16:00+00:00',
  resolved: false,
  resolved_at: null,
  order_status: 'PLACED',
  order_total_cents: 2650,
  order_created_at: '2026-11-07T18:00:00+00:00',
}

export const stats = {
  currency: 'EUR',
  date_from: null,
  date_to: null,
  placed_order_count: 4,
  orders_by_status: {
    PLACED: 1,
    ACCEPTED: 0,
    PREPARING: 0,
    READY: 0,
    ASSIGNED: 0,
    OUT_FOR_DELIVERY: 1,
    DELIVERED: 1,
    CANCELLED: 1,
    REFUNDED: 0,
  },
  gross_mock_paid_cents: 10600,
  refunded_cents: 2650,
  net_retained_cents: 7950,
  delivered_count: 1,
  items_sold: 9,
  avg_order_value_cents: 2650,
}
