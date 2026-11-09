"""String constants for roles and the three state machines (D18: strings).

Order status   : orders.status          (9 values, D7 central machine)
Payment status : orders.payment_status  (2 values; `refunded` reached two
                    ways — cancellation D29 and approved refund D30)
Refund status  : refund_requests.status (3 values, D28)
"""

# User roles (D2: public registration may only create `customer`).
ROLE_CUSTOMER = "customer"
ROLE_OWNER = "restaurant_owner"
ROLE_PARTNER = "delivery_partner"
ROLES = (ROLE_CUSTOMER, ROLE_OWNER, ROLE_PARTNER)

# Order status (brief §4 lifecycle + CANCELLED/REFUNDED).
ORDER_PLACED = "PLACED"
ORDER_ACCEPTED = "ACCEPTED"
ORDER_PREPARING = "PREPARING"
ORDER_READY = "READY"
ORDER_ASSIGNED = "ASSIGNED"
ORDER_OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
ORDER_DELIVERED = "DELIVERED"
ORDER_CANCELLED = "CANCELLED"
ORDER_REFUNDED = "REFUNDED"
ORDER_STATUSES = (
    ORDER_PLACED,
    ORDER_ACCEPTED,
    ORDER_PREPARING,
    ORDER_READY,
    ORDER_ASSIGNED,
    ORDER_OUT_FOR_DELIVERY,
    ORDER_DELIVERED,
    ORDER_CANCELLED,
    ORDER_REFUNDED,
)

# Payment status (D29: no `void` — `refunded` is disambiguated by order status).
PAYMENT_MOCK_PAID = "mock_paid"
PAYMENT_REFUNDED = "refunded"
PAYMENT_STATUSES = (PAYMENT_MOCK_PAID, PAYMENT_REFUNDED)

# Refund-request status (brief §5).
REFUND_PENDING = "pending"
REFUND_APPROVED = "approved"
REFUND_REJECTED = "rejected"
REFUND_STATUSES = (REFUND_PENDING, REFUND_APPROVED, REFUND_REJECTED)

# Money (D3, D26): all values are integer minor units of this one currency.
CURRENCY = "EUR"
CURRENCY_SYMBOL = "€"
