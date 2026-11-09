"""Initial schema — the nine tables of docs/database.md (approved design).

Revision ID: 0001
Revises:
Create Date: 2026-11-07

Tables (brief §10's eight + `refund_requests`, the justified 9th):
users, restaurants, menu_items, orders, order_items, payment_ledger,
refund_requests, reviews, reminder_logs.

Conventions: integer-cents money (D3/D26), string statuses (D18),
UTC timestamps set by the application (D33), FKs RESTRICT, and the
integrity constraints documented in docs/database.md §1/§6.

Timestamp DDL note (D33): the columns are plain ``DATETIME`` in DDL. The
*storage contract* (aware-UTC values written as
``YYYY-MM-DD HH:MM:SS.ffffff +00:00`` and read back aware) is implemented
by the runtime type ``app.db.types.UTCDateTime`` used in the ORM models;
it emits identical DDL, so no separate migration revision is required.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "role IN ('customer', 'restaurant_owner', 'delivery_partner')",
            name="ck_users_role",
        ),
    )
    op.create_index("ix_users_role_active", "users", ["role", "is_active"])

    op.create_table(
        "restaurants",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("delivery_fee_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("owner_id", name="uq_restaurants_owner"),
        sa.CheckConstraint("delivery_fee_cents >= 0", name="ck_restaurants_fee"),
    )

    op.create_table(
        "menu_items",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("price_cents >= 0", name="ck_menu_price"),
    )
    op.create_index("ix_menu_rest_avail", "menu_items", ["restaurant_id", "available"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), nullable=False),
        sa.Column("delivery_partner_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payment_status", sa.String(length=20), nullable=False),
        sa.Column("status_updated_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("items_subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("delivery_fee_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("delivery_address", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["restaurant_id"], ["restaurants.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["delivery_partner_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "status IN ('PLACED', 'ACCEPTED', 'PREPARING', 'READY', 'ASSIGNED', "
            "'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED', 'REFUNDED')",
            name="ck_orders_status",
        ),
        sa.CheckConstraint(
            "payment_status IN ('mock_paid', 'refunded')",
            name="ck_orders_payment_status",
        ),
        sa.CheckConstraint("items_subtotal_cents >= 0", name="ck_orders_subtotal"),
        sa.CheckConstraint("delivery_fee_cents >= 0", name="ck_orders_fee"),
        sa.CheckConstraint(
            "total_cents = items_subtotal_cents + delivery_fee_cents "
            "AND total_cents >= 0",
            name="ck_orders_total_identity",
        ),
        sa.UniqueConstraint(
            "customer_id", "idempotency_key", name="uq_orders_customer_key"
        ),
    )
    op.create_index("ix_orders_customer_created", "orders", ["customer_id", "created_at"])
    op.create_index("ix_orders_customer_status", "orders", ["customer_id", "status"])
    op.create_index("ix_orders_restaurant_status", "orders", ["restaurant_id", "status"])
    op.create_index("ix_orders_restaurant_created", "orders", ["restaurant_id", "created_at"])
    op.create_index("ix_orders_status_updated", "orders", ["status", "status_updated_at"])
    op.create_index("ix_orders_partner_status", "orders", ["delivery_partner_id", "status"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("menu_item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(length=120), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total_cents", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["menu_item_id"], ["menu_items.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_order_items_price"),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_qty"),
        sa.CheckConstraint(
            "line_total_cents = unit_price_cents * quantity "
            "AND line_total_cents >= 0",
            name="ck_order_items_line_identity",
        ),
    )
    op.create_index("ix_order_items_order", "order_items", ["order_id"])

    op.create_table(
        "payment_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "type IN ('mock_paid', 'refunded')", name="ck_ledger_type"
        ),
        sa.CheckConstraint("amount_cents >= 0", name="ck_ledger_amount"),
        sa.UniqueConstraint("order_id", "type", name="uq_ledger_order_type"),
    )
    op.create_index("ix_ledger_order", "payment_ledger", ["order_id"])

    op.create_table(
        "refund_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_refunds_status",
        ),
        sa.UniqueConstraint("order_id", name="uq_refunds_order"),
    )
    op.create_index("ix_refunds_status", "refund_requests", ["status"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating"),
        sa.UniqueConstraint("order_id", name="uq_reviews_order"),
    )
    op.create_index("ix_reviews_customer", "reviews", ["customer_id"])

    op.create_table(
        "reminder_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("status_at_reminder", sa.String(length=20), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status_at_reminder IN ('PLACED', 'ACCEPTED')",
            name="ck_reminders_status",
        ),
        sa.UniqueConstraint(
            "order_id", "status_at_reminder", name="uq_reminders_episode"
        ),
    )
    op.create_index("ix_reminders_resolved", "reminder_logs", ["resolved"])
    op.create_index("ix_reminders_order", "reminder_logs", ["order_id"])


def downgrade() -> None:
    # The baseline is dropped in reverse creation order.
    for index in (
        "ix_reminders_order",
        "ix_reminders_resolved",
    ):
        op.drop_index(index, table_name="reminder_logs")
    op.drop_table("reminder_logs")
    for index in ("ix_reviews_customer",):
        op.drop_index(index, table_name="reviews")
    op.drop_table("reviews")
    for index in ("ix_refunds_status",):
        op.drop_index(index, table_name="refund_requests")
    op.drop_table("refund_requests")
    for index in ("ix_ledger_order",):
        op.drop_index(index, table_name="payment_ledger")
    op.drop_table("payment_ledger")
    for index in ("ix_order_items_order",):
        op.drop_index(index, table_name="order_items")
    op.drop_table("order_items")
    for index in (
        "ix_orders_partner_status",
        "ix_orders_status_updated",
        "ix_orders_restaurant_created",
        "ix_orders_restaurant_status",
        "ix_orders_customer_status",
        "ix_orders_customer_created",
    ):
        op.drop_index(index, table_name="orders")
    op.drop_table("orders")
    for index in ("ix_menu_rest_avail",):
        op.drop_index(index, table_name="menu_items")
    op.drop_table("menu_items")
    op.drop_table("restaurants")
    for index in ("ix_users_role_active",):
        op.drop_index(index, table_name="users")
    op.drop_table("users")
