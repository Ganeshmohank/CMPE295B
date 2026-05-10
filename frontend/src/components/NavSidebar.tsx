import { useCallback, useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { api } from '../api'
import { SUMMARY_STALE_EVENT } from '../lib/summarySync'
import { InitialAvatar } from './InitialAvatar'
import { DEMO_USER } from '../lib/demoUser'

export function NavSidebar() {
  const [pending, setPending] = useState<number | null>(null)
  const location = useLocation()

  const refreshPending = useCallback(() => {
    let alive = true
    api
      .summary(7)
      .then((d) => {
        if (alive) setPending(d.total_pending_reviews)
      })
      .catch(() => {
        if (alive) setPending(null)
      })
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    const cancel = refreshPending()
    return cancel
  }, [location.pathname, refreshPending])

  useEffect(() => {
    const onStale = () => {
      void api.summary(7).then((d) => setPending(d.total_pending_reviews)).catch(() => setPending(null))
    }
    window.addEventListener(SUMMARY_STALE_EVENT, onStale)
    return () => window.removeEventListener(SUMMARY_STALE_EVENT, onStale)
  }, [])

  return (
    <aside className="sidebar">
      <div className="sidebar__top">
        <div className="brand">Meeting intelligence</div>
        <p className="sidebar-tagline">Transcripts → actions → review</p>
      </div>
      <nav className="sidebar__nav" aria-label="Primary">
        <NavLink className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')} to="/" end>
          Dashboard
        </NavLink>
        <NavLink className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')} to="/meetings">
          Meetings
        </NavLink>
        <NavLink className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')} to="/activity">
          Activity
        </NavLink>
        <NavLink className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')} to="/review">
          <span className="nav-link__row">
            Review queue
            {pending != null && pending > 0 && (
              <span className="nav-badge">{pending > 99 ? '99+' : pending}</span>
            )}
          </span>
        </NavLink>
        <NavLink className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')} to="/logs">
          Pipeline logs
        </NavLink>
        <NavLink className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')} to="/connected-apps">
          Connected apps
        </NavLink>
      </nav>
      <div className="sidebar__footer">
        <NavLink
          className={({ isActive }) => 'sidebar-profile-link' + (isActive ? ' sidebar-profile-link--active' : '')}
          to="/profile"
        >
          <InitialAvatar name={DEMO_USER.displayName} className="initial-avatar--sidebar" />
          <span className="sidebar-profile-link__text">
            <span className="sidebar-profile-link__name">{DEMO_USER.displayName}</span>
            <span className="sidebar-profile-link__hint">View profile</span>
          </span>
        </NavLink>
      </div>
    </aside>
  )
}
