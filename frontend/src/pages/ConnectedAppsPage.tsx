import { Link } from 'react-router-dom'

type ConnStatus = 'connected' | 'coming_soon'

/** simple-icons slug / npm icon filename (no .svg) — https://simpleicons.org */
interface IntegrationItem {
  id: string
  name: string
  status: ConnStatus
  iconSlug: string
}

const SI_CDN = (slug: string) =>
  `https://cdn.jsdelivr.net/npm/simple-icons@11.14.0/icons/${slug}.svg`

const CONNECTED: IntegrationItem[] = [
  { id: 'jira', name: 'Jira', status: 'connected', iconSlug: 'jira' },
  { id: 'confluence', name: 'Confluence', status: 'connected', iconSlug: 'confluence' },
  { id: 'notion', name: 'Notion', status: 'connected', iconSlug: 'notion' },
  { id: 'gcal', name: 'Google Calendar', status: 'connected', iconSlug: 'googlecalendar' },
  { id: 'zoom', name: 'Zoom', status: 'connected', iconSlug: 'zoom' },
]

const UPCOMING: IntegrationItem[] = [
  { id: 'slack', name: 'Slack', status: 'coming_soon', iconSlug: 'slack' },
  { id: 'teams', name: 'Microsoft Teams', status: 'coming_soon', iconSlug: 'microsoftteams' },
  { id: 'linear', name: 'Linear', status: 'coming_soon', iconSlug: 'linear' },
  { id: 'hubspot', name: 'HubSpot', status: 'coming_soon', iconSlug: 'hubspot' },
]

function IntegrationCard({ item }: { item: IntegrationItem }) {
  const connected = item.status === 'connected'
  return (
    <article
      className={
        'integration-card' + (connected ? ' integration-card--live' : ' integration-card--soon')
      }
    >
      <div className="integration-card__logo-wrap" aria-hidden>
        <img
          src={SI_CDN(item.iconSlug)}
          alt=""
          className="integration-card__logo"
          loading="lazy"
          decoding="async"
        />
      </div>
      <div className="integration-card__main">
        <h3 className="integration-card__title">{item.name}</h3>
        <span className={'integration-card__badge' + (connected ? ' integration-card__badge--ok' : '')}>
          {connected ? 'Connected' : 'Coming soon'}
        </span>
      </div>
    </article>
  )
}

export function ConnectedAppsPage() {
  return (
    <div className="page-connected-apps">
      <header className="page-connected-apps__header">
        <h1>Connected apps</h1>
        <p className="muted page-connected-apps__lede">
          Products linked to Meeting intelligence for meetings, orchestration, and recaps.{' '}
          <Link to="/profile">Profile</Link> shows how team access maps to this workspace.
        </p>
      </header>

      <section className="integrations-section" aria-labelledby="integrations-active-heading">
        <h2 id="integrations-active-heading" className="integrations-section__title">
          Active connections
        </h2>
        <p className="integrations-section__sub muted">In use with your workspace today.</p>
        <div className="integrations-grid">
          {CONNECTED.map((item) => (
            <IntegrationCard key={item.id} item={item} />
          ))}
        </div>
      </section>

      <section className="integrations-section" aria-labelledby="integrations-soon-heading">
        <h2 id="integrations-soon-heading" className="integrations-section__title">
          Upcoming connectors
        </h2>
        <p className="integrations-section__sub muted">Planned next — not wired in this build.</p>
        <div className="integrations-grid integrations-grid--soon">
          {UPCOMING.map((item) => (
            <IntegrationCard key={item.id} item={item} />
          ))}
        </div>
      </section>
    </div>
  )
}
