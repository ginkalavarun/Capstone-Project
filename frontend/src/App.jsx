import { Link, NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import { useCart } from './context/CartContext.jsx'
import { RequireAuth } from './components/RequireAuth.jsx'
import { ROLES } from './lib/roles.js'

import Home from './pages/Home.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Restaurants from './pages/Restaurants.jsx'
import Menu from './pages/Menu.jsx'
import Cart from './pages/CartPage.jsx'
import Checkout from './pages/Checkout.jsx'
import CustomerOrders from './pages/CustomerOrders.jsx'
import CustomerOrderDetail from './pages/CustomerOrderDetail.jsx'
import Insights from './pages/Insights.jsx'
import OwnerLayout from './pages/OwnerLayout.jsx'
import OwnerOrders from './pages/OwnerOrders.jsx'
import OwnerOrderDetail from './pages/OwnerOrderDetail.jsx'
import OwnerMenu from './pages/OwnerMenu.jsx'
import OwnerReminders from './pages/OwnerReminders.jsx'
import OwnerStats from './pages/OwnerStats.jsx'
import DeliveryLayout from './pages/DeliveryLayout.jsx'
import DeliveryActive from './pages/DeliveryActive.jsx'
import DeliveryHistory from './pages/DeliveryHistory.jsx'
import DeliveryOrderDetail from './pages/DeliveryOrderDetail.jsx'
import Forbidden from './pages/Forbidden.jsx'
import NotFound from './pages/NotFound.jsx'

const NAV = {
  [ROLES.CUSTOMER]: [
    ['/restaurants', 'Browse'],
    ['/cart', 'Cart'],
    ['/orders', 'My orders'],
    ['/insights', 'Insights'],
  ],
  [ROLES.OWNER]: [
    ['/owner/orders', 'Orders'],
    ['/owner/menu', 'Menu'],
    ['/owner/reminders', 'Reminders'],
    ['/owner/stats', 'Stats'],
  ],
  [ROLES.PARTNER]: [
    ['/delivery', 'Deliveries'],
    ['/delivery/history', 'History'],
  ],
}

/**
 * App shell: brand, role-based navigation (FE-04), user + logout, and the
 * route table. Route guards are UX convenience — the backend enforces
 * every rule (D8).
 */
export default function App() {
  const { user, logout } = useAuth()
  const { itemCount } = useCart()
  const navigate = useNavigate()

  const links = user ? NAV[user.role] ?? [] : []

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          CampusBite
        </Link>
        <nav className="main-nav" aria-label="Main navigation">
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} className="nav-link">
              {label}
              {to === '/cart' && itemCount > 0 ? (
                <span className="badge badge-cart">{itemCount}</span>
              ) : null}
            </NavLink>
          ))}
        </nav>
        {user ? (
          <span className="userbox">
            <span className="muted">
              {user.full_name} <span className="role-chip">{user.role.replace(/_/g, ' ')}</span>
            </span>
            <button
              type="button"
              className="btn"
              onClick={() => {
                logout()
                navigate('/')
              }}
            >
              Log out
            </button>
          </span>
        ) : (
          <span className="userbox">
            <Link className="nav-link" to="/login">
              Log in
            </Link>
            <Link className="nav-link" to="/register">
              Register
            </Link>
          </span>
        )}
      </header>

      <main id="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          {/* Public catalog (D16). */}
          <Route path="/restaurants" element={<Restaurants />} />
          <Route path="/restaurants/:id" element={<Menu />} />

          {/* Customer */}
          <Route
            path="/cart"
            element={
              <RequireAuth roles={[ROLES.CUSTOMER]}>
                <Cart />
              </RequireAuth>
            }
          />
          <Route
            path="/checkout"
            element={
              <RequireAuth roles={[ROLES.CUSTOMER]}>
                <Checkout />
              </RequireAuth>
            }
          />
          <Route
            path="/orders"
            element={
              <RequireAuth roles={[ROLES.CUSTOMER]}>
                <CustomerOrders />
              </RequireAuth>
            }
          />
          <Route
            path="/orders/:id"
            element={
              <RequireAuth roles={[ROLES.CUSTOMER]}>
                <CustomerOrderDetail />
              </RequireAuth>
            }
          />
          <Route
            path="/insights"
            element={
              <RequireAuth roles={[ROLES.CUSTOMER]}>
                <Insights />
              </RequireAuth>
            }
          />

          {/* Owner */}
          <Route
            path="/owner"
            element={
              <RequireAuth roles={[ROLES.OWNER]}>
                <OwnerLayout />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/owner/orders" replace />} />
            <Route path="orders" element={<OwnerOrders />} />
            <Route path="orders/:id" element={<OwnerOrderDetail />} />
            <Route path="menu" element={<OwnerMenu />} />
            <Route path="reminders" element={<OwnerReminders />} />
            <Route path="stats" element={<OwnerStats />} />
          </Route>

          {/* Delivery partner */}
          <Route
            path="/delivery"
            element={
              <RequireAuth roles={[ROLES.PARTNER]}>
                <DeliveryLayout />
              </RequireAuth>
            }
          >
            <Route index element={<DeliveryActive />} />
            <Route path="history" element={<DeliveryHistory />} />
            <Route path="orders/:id" element={<DeliveryOrderDetail />} />
          </Route>

          <Route path="/forbidden" element={<Forbidden />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}
