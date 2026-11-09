import { NavLink, Outlet } from 'react-router-dom'

const TABS = [
  ['/owner/orders', 'Orders'],
  ['/owner/menu', 'Menu'],
  ['/owner/reminders', 'Reminders'],
  ['/owner/stats', 'Stats'],
]

/** Owner sub-navigation (FE-11): dashboard tabs + the matched page. */
export default function OwnerLayout() {
  return (
    <div>
      <nav className="tabs" aria-label="Owner dashboard">
        {TABS.map(([to, label]) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => (isActive ? 'tab active' : 'tab')}
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  )
}
