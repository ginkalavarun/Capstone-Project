# CampusBite — Assignment Brief (Reference)

> **Source:** `Capstone Project.pdf` (12 pages), extracted in full. This is the
> authoritative assignment. When this file and the PDF disagree, the PDF wins and
> this file must be corrected.
>
> **Companion docs:** decisions, requirements, authorization-matrix, test-plan,
> architecture, milestones, excluded-features, assumptions, progress.

## Problem statement

Develop a full-stack restaurant ordering and delivery application called
**CampusBite**. Customers explore restaurants, browse menus, place orders, and
track order status. Restaurant owners manage menus and orders. Delivery partners
manage their assigned deliveries.

Three user types, each with role-based access: **Customer**, **Restaurant
Owner**, **Delivery Partner**.

## 1. Technology stack

| Layer | Required |
|---|---|
| Frontend | React.js, JavaScript (ES6+), React Hooks, React Router DOM, Fetch or Axios |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy ORM, JWT auth, Docker + Docker Compose |
| Database | SQL-based relational database; SQLAlchemy for operations |
| AI | OpenAI API |
| Version control | Git and GitHub |

## 2. Functional requirements by role

### A. Customer
1. Register and log in.
2. Browse available restaurants.
3. View restaurant menus and food details.
4. Search and filter dishes by name and price.
5. Add dishes to cart.
6. Update or remove cart items.
7. Place orders using a dummy payment system.
8. View order history.
9. Track order status.
10. Cancel orders when cancellation is allowed.
11. Submit ratings/reviews after successful delivery.
12. Request a return/refund after an order is delivered.
13. View AI-generated summaries and insights about their previous orders.

### B. Restaurant Owner
1. Log in.
2. Add new dishes to the restaurant menu.
3. View, update, and manage existing dishes.
4. Mark dishes available or unavailable.
5. View incoming orders for their restaurant.
6. Accept orders and update preparation status.
7. Assign delivery partners to orders.
8. Filter orders by status and date.
9. View basic restaurant statistics.
10. Approve or reject customer return/refund requests.
11. View reminders for orders not updated for a specified period.

### C. Delivery Partner
1. Log in.
2. View only orders assigned to them.
3. View customer delivery details.
4. Update order status to Out for Delivery.
5. Mark orders as Delivered.
6. View delivery history.

## 3. Authentication and authorization (RBAC)

- Register and log in.
- Password hashing with **bcrypt**.
- **JWT** tokens for authentication.
- Three roles: Customer, Restaurant Owner, Delivery Partner.
- Protect frontend pages by role.
- Protect backend APIs with authentication **and** authorization.
- Users may only access data they are authorized to view or modify.
- Store the token in **localStorage** and send it with protected requests.
- **Hiding buttons/pages on the frontend is not sufficient. Authorization must
  also be implemented on the backend.**

## 4. Order management and lifecycle

Lifecycle: `PLACED → ACCEPTED → PREPARING → READY → ASSIGNED →
OUT_FOR_DELIVERY → DELIVERED`. Additional statuses: `CANCELLED`, `REFUNDED`.

Rules:
- Customers can cancel **only when the order is PLACED**.
- Owners accept orders and update preparation status.
- Owners assign delivery partners **when an order is READY**.
- Delivery partners update **only their assigned** orders.
- Partners move `ASSIGNED → OUT_FOR_DELIVERY → DELIVERED`.
- **Delivered orders cannot be cancelled.**
- **Invalid transitions must be rejected by the backend.**

## 5. Dummy payment and return/refund

**Dummy payment** (no real gateway):
- Place orders without real payment.
- On successful placement, set payment status to `mock_paid`.
- Maintain a payment record to track dummy payments.

**Return / refund:**
- Request **only after the order is delivered**.
- Customer must provide a **reason**.
- Owner approves or rejects.
- Approved → payment status `refunded` + a refund record.
- Rejected → return status `rejected`.
- **No multiple return requests for the same order.**

## 6. Dashboard and filtering

Separate dashboards for all three roles.

- **Customer:** previous/current orders; filter by status and date; view
  payment and return/refund status; cancel eligible orders; submit reviews and
  return requests.
- **Restaurant owner:** incoming orders; filter by status and date; manage
  menu; assign partners; basic statistics; manage return/refund requests.
- **Delivery partner:** assigned deliveries; filter by status; update delivery
  status; delivery history.

**Pagination wherever required** for large lists.

## 7. Applied AI — order insights (OpenAI)

- Customers request summaries of previous orders and ask questions about order history.
- Backend fetches the **authenticated customer's** order details from the DB.
- Sends relevant order info to OpenAI; displays the response in React.
- **Customers cannot access another customer's data via the AI feature.**
- Store the OpenAI key securely in **backend** environment variables.
- Basic error handling and **rate-limit** handling.

Example queries: "Summarize my last five orders", "Which orders are not
delivered?", "How much did I spend this week?", "Which items did I order most?"

The AI uses the customer's **actual** order history as context. Embeddings,
vector DBs, or RAG are **not required**.

## 8. Backend middleware and background tasks

**Middleware (FastAPI):**
- Log incoming request methods and API paths.
- Measure API response time.
- Handle request-level processing where needed.

**Background tasks — owner reminders:**
- Remind owners about orders not updated for **> 15 minutes**.
- Identify orders still in `PLACED` or `ACCEPTED`.
- Generate reminder records; display them on the owner dashboard.
- **Real-time notifications and WebSockets are not required.**

## 9. React frontend requirements

- Reusable components.
- Hooks: `useState`, `useEffect`, `useContext`.
- React Router DOM for navigation.
- Separate pages/dashboards per role.
- Manage cart and user data with basic React state.
- Integrate backend REST APIs via Fetch or Axios.
- Loading states and error handling.
- Persist login info in **localStorage**.
- Send JWT with protected requests.
- Protected routes and role-based navigation.
- **Responsive** across desktop and mobile.

Suggested pages: Login/Register, Restaurant Listing, Restaurant Menu, Cart &
Checkout, Customer Dashboard, Owner Dashboard, Menu Management, Order
Management, Delivery Partner Dashboard, AI Order Insights.

> Redux/Zustand are **not mandatory**; built-in hooks suffice.

## 10. Database requirements

Relational SQL database via SQLAlchemy. Tables:
**Users, Restaurants, Menu Items, Orders, Order Items, Reviews, Payment
Ledger, Admin Reminder Logs.**

Relationships:
- A customer → many orders.
- A restaurant → many menu items and many orders.
- An order → many order items.
- A delivered order → **one** review.
- An order → **many** payment ledger entries.
- A delivery partner → **many** orders (assigned).

Establish appropriate PKs, FKs, and relationships. Use SQL/SQLAlchemy for
CRUD.

## 11. Backend Dockerization

- Dockerfile for the FastAPI backend.
- `docker-compose.yml` to run the backend.
- Configure required environment variables.
- App must start correctly in the container.
- Expose the required backend port.
- Backend must connect to the SQL database.
- **Keep secrets (API keys, DB credentials, JWT secrets) out of the image and
  the repo.**
- Provide an **`.env.example`** with variable names, no real values.
- **Runnable locally with Docker Compose.**

## 12. API development (REST, FastAPI)

APIs for: user registration & auth; restaurant listing & menu management;
order placement; order history & details; order status management; delivery
partner assignment; reviews & ratings; return/refund management; AI order
insights; restaurant statistics & reminders.

Implement proper request validation, response handling, and HTTP status codes.
**All business rules and authorization checks enforced on the backend.**

## 13. Deployment and documentation

The GitHub repo must contain: complete React frontend, complete FastAPI
backend, Dockerfile, docker-compose.yml, `.env.example` files, and a
**README.md** with: project overview; technologies; features implemented;
how to run the frontend locally; how to run the backend with Docker Compose;
required env vars; database setup; API documentation details.

**No sensitive information (keys, passwords, DB credentials) in the repo.**

## 14. Expected outcome

A functional full-stack app where customers browse/order/track/review; owners
manage menus/orders/refunds; delivery partners manage their deliveries;
customers access AI insights; proper auth & authorization; React↔FastAPI via
REST; FastAPI containerized; data in a relational SQL database.

## Submission

- **Public** GitHub repository URL only.
- Frontend, backend, Dockerfile, docker-compose.yml, README.md all present.
- No secrets in the repo.
- The application must run correctly and the repo must be accessible to the
  evaluation team before submission.
