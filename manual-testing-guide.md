# CampusBite — Manual Testing Guide (step by step)

Walk through the whole platform by hand, role by role, in a real browser.
Everything here matches the running app: URLs, button labels, and the status
values you will see on screen.

**Accounts** — the privileged accounts were provisioned inside the Docker
container and their generated passwords are saved in
**`demo-credentials.txt`** in the project root (git-ignored; read it there,
do not paste it anywhere else):

| Role | Email | Password |
|---|---|---|
| Restaurant owner (Slice House) | `owner@example.com` | in `demo-credentials.txt` |
| Delivery partner | `partner@example.com` | in `demo-credentials.txt` |
| Customer | register your own (Scenario 1) | you choose it |

## 0. Start the app & set up your browser

1. Backend (Docker):
   ```bash
   docker compose up -d --build     # from the project root
   curl -s http://localhost:8000/api/v1/health    # → {"status":"ok"}
   ```
2. Frontend:
   ```bash
   cd frontend && npm run dev       # → http://localhost:5173
   ```
3. **One browser window = one login** (the JWT lives in that window's
   localStorage). To play several roles *at once*, open:
   - a normal window → **customer**
   - two incognito/private windows → **owner** and **partner**
   Or just log out / log in the same window between scenarios (the data is
   server-side, so nothing is lost).

Current demo data: the restaurant **Slice House** (€2.50 delivery fee) has
two dishes — *Margherita Slice* €7.50 and *Berry Smoothie* €4.00 — created
during verification. If your container's database is empty, run Scenario 0
first.

---

## Scenario 0 — Owner: menu management (skip if the menu already has dishes)

1. Log in as the owner → top nav shows *Orders / Menu / Reminders / Stats*.
2. **Menu** — you see the existing dishes with price, description,
   *Available / Not available*.
3. Add a dish: fill **Name**, **Description**, **Price (€)**, keep *Available*
   ticked → **Add dish**. It appears in the list.
4. Toggle a dish off: **Not available** button → it flips to *Available*.
   (Dishes are deactivated, never deleted — past orders keep their snapshots.)
5. Edit a dish: **Edit** → change the price → **Save**. Then check a *past*
   order (any) — its item line still shows the old price. That is the
   historical snapshot working.

---

## Scenario 1 — Customer: browse, search, filter, cart, checkout

1. (Customer window) **Register** — full name, email, password (8+ chars) →
   you are logged in; top nav shows *Browse / Cart / My orders / Insights*.
2. **Browse** → *Slice House* card → **View menu**.
3. **Search by name** — type `marg` → only *Margherita Slice* remains.
   Clear it.
4. **Price filters** — min `5`, max `10` → only the €7.50 dish shows;
   min `0`, max `5` → only the €4.00 dish; clear both → all dishes.
   *(Unavailable dishes show "Not available" instead of an add button.)*
5. **Cart** — **Add to cart** on both dishes; on the cart page use the
   **+/−** steppers (e.g. 2× Margherita, 1× Smoothie).
   Total (estimated) = 2×€7.50 + 1×€4.00 = **€19.00** (the final total adds
   the €2.50 fee at checkout, calculated on the server).
6. **Proceed to checkout** → enter a delivery address (max 255 chars) →
   **Place order**.
7. Expected: success confirmation. **My orders** now shows the order with
   status **PLACED** and the server-computed total (19.00 + 2.50 = **€21.50**).
   The item lines show names + prices *as ordered*, not live menu values.

---

## Scenario 2 — Owner: receive and prepare the order

1. (Owner window) **Orders** → the new order appears, **PLACED**, with the
   customer name, items, address, total.
2. Open it → **Accept** → confirm dialog (*Accept order*) → status **ACCEPTED**.
3. **Start preparing** → **PREPARING**.
4. **Mark ready** → **READY**.
   - While **PLACED** only, the customer can still cancel (Scenario 6).
     From ACCEPTED onward the customer no longer sees a cancel button.
   - Try an out-of-order action (e.g. reload and click again): the backend
     rejects invalid transitions — you get an error notice, the status stays.

---

## Scenario 3 — Owner: assign the delivery partner

1. On the **READY** order: **Assign to** dropdown lists active partners
   (names only — no emails or other personal data) → pick *Dana Kim* →
   **Assign** → confirm (*Confirm assignment*) → status **ASSIGNED**.
2. Negative checks (optional): assign again → rejected (already assigned);
   a customer or the partner can never assign (role check).

---

## Scenario 4 — Partner: deliver

1. (Partner window) **Deliveries** → the order appears, **ASSIGNED**, with
   the customer's name and delivery address (the partner needs these to
   deliver; everything else stays private).
2. Open it → **Start delivery** → confirm (*Out for delivery*) →
   **OUT FOR DELIVERY**.
3. **Mark delivered** → confirm (*Delivered*) → **DELIVERED**, and a
   *delivered at* timestamp appears.
4. **History** (nav) now lists it. *Deliveries* shows active work only.
5. Negative: a *second* partner (or the customer) opening that order URL
   directly gets a 404 — only the assigned partner acts on deliveries.

---

## Scenario 5 — Customer: review, then request & get a refund

1. (Customer window) **My orders** → open the **DELIVERED** order.
2. **Review** (available once delivered): pick a star rating, add a comment →
   submit → *Thanks for your review!* It now shows below; you cannot submit a
   second one (one review per order).
3. **Request refund**: fill *Why do you want a refund?* (non-empty) →
   **Request refund** → notice: *Your refund request is pending…*.
4. (Owner window) **Orders** → open the order → the **Refund request (pending)**
   block shows the customer's reason → **Approve refund**.
5. Back to the customer order: status **REFUNDED** and the notice
   *Your refund was approved — the full total (including the delivery fee)
   was reversed.* The review from step 2 is still visible (refunds never
   erase reviews).
6. **Reject variant** (on another delivered order): owner clicks **Reject** →
   the customer sees *rejected … one request per order* and the order stays
   DELIVERED / paid.

---

## Scenario 6 — Customer: cancel while PLACED

1. (Customer) place **another** order (Scenario 1, any items) → **PLACED**.
   *Do not* let the owner accept it.
2. Open the order → **Cancel order** → confirm (*Yes, cancel*) →
   **CANCELLED**, notice: *the mock payment was reversed.*
3. (Owner) **Orders** → it shows **CANCELLED**. Note: cancellation is *not* a
   refund request — no pending refund appears, but the payment was reversed.
4. Negative: after the owner has accepted the *other* order, its cancel
   button is gone and the API would reject the cancel anyway (PLACED only).

---

## Scenario 7 — Owner: statistics, filters, reminders

1. **Stats** — cards for order counts by status plus money in cents/EUR:
   gross mock-paid, refunded, net retained, delivered count.
2. **Orders** — use the **status** dropdown (e.g. DELIVERED) and/or the
   from/to date fields → **Apply filters**; use **Prev/Next** for pagination.
3. **Reminders** — the scanner (runs every 60 s) lists *stale* orders that
   have sat in **PLACED** or **ACCEPTED** for more than **15 minutes**.
   To see one for real: place an order, *don't* accept it, wait ~16 minutes,
   then open **Reminders**. (Only your restaurant's orders, owner-only.)

---

## Scenario 8 — Customer: AI order insights

1. (Customer) **Insights** page.
2. **Without** an OpenAI key (current setup): you see a *not configured*
   notice **plus** the exact figures the app computes (orders, spend,
   favourite dish, …) — the app works fully without a key.
3. **With** a key (`OPENAI_API_KEY` in the root `.env` and `backend/.env`,
   then `docker compose up -d` to re-inject): ask a question like
   "How much did I spend last month?" → a real AI answer appears, based only
   on *your* orders. Watch the rate-limit message if you spam it, and note
   the answer never invents totals — money figures come from the app.

---

## Scenario 9 — Quick security spot-checks

- Open `http://localhost:5173/owner/orders` **while logged out** → you are
  sent to the login screen (route guard).
- While logged in as the **partner**, manually edit the URL to
  `/orders/<some customer order id>` → you cannot read it (404/forbidden).
- Register a **second customer**; open the first customer's order URL in the
  second customer's window → 404. Roles alone never grant access to
  someone else's resources.
- As a customer, open `/owner/stats` or `/delivery` directly → you cannot.

---

## Status flow at a glance

```
            (customer, PLACED only)
            ▼
PLACED → ACCEPTED → PREPARING → READY → ASSIGNED → OUT_FOR_DELIVERY → DELIVERED
   │                                                              │
   │                      (customer request, owner decision)      │
   ▼                                                              ▼
CANCELLED (payment reversed)                        REFUNDED (if approved)
```

- **Review** becomes possible from DELIVERED (and survives a later refund).
- **Refund request**: one per order, only after DELIVERED while none exists.
- **Assignment**: only from READY, only by the owner, only to active partners.
- **Delivery updates**: only by the assigned partner.

## If you want a clean slate

- New orders/roles: just keep going — nothing resets.
- Wipe everything (destroys the demo data, including provisioned accounts):
  `docker compose down -v` then `docker compose up -d --build` and redo
  provisioning (README *Creating accounts*). Use only if you really want to.
