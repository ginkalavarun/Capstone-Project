import { NavLink, Outlet } from 'react-router-dom'

/** Delivery sub-navigation (FE-12): active workload + history tabs. */
export default function DeliveryLayout() {
  return (
    <div>
      <nav className="tabs" aria-label="Delivery dashboard">
        <NavLink to="/delivery" end className={({ isActive }) => (isActive ? 'tab active' : 'tab')}>
          Active
        </NavLink>
        <NavLink
          to="/delivery/history"
          className={({ isActive }) => (isActive ? 'tab active' : 'tab')}
        >
          History
        </NavLink>
      </nav>
      <Outlet />
    </div>
  )
}
