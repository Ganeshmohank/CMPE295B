import { Link } from 'react-router-dom'

/** Demo profile — replace with auth + `/api/me` when you add accounts. */
const DEMO_USER = {
  displayName: 'Alex Rivera',
  email: 'alex.rivera@company.example',
  title: 'Engineering lead',
  timezone: 'America/Los_Angeles',
  primaryTeam: {
    name: 'Platform & integrations',
    id: 'team_platform',
    role: 'Lead',
    description: 'Owns Meeting intelligence pipelines, MCP connectors, and review workflows.',
  },
  orgTeams: [
    {
      team: 'Platform & integrations',
      role: 'Lead',
      access: 'Admin — meetings, projects, orchestration, connected apps',
    },
    {
      team: 'Customer programs',
      role: 'Contributor',
      access: 'Read/write meeting context; approve action items for assigned initiatives',
    },
    {
      team: 'Security review',
      role: 'Viewer',
      access: 'Read-only meetings and activity for SCRUM / compliance initiatives',
    },
  ],
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase()
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase()
}

export function UserProfilePage() {
  const u = DEMO_USER
  return (
    <div className="page-profile">
      <header className="page-profile__header">
        <h1>Profile</h1>
        <p className="muted page-profile__lede">
          Demo workspace identity. Hook this page to your SSO or directory when you add real auth.
        </p>
      </header>

      <div className="page-profile__grid">
        <section className="panel panel--elevated page-profile__card" aria-labelledby="profile-me-heading">
          <h2 id="profile-me-heading" className="panel__h">
            You
          </h2>
          <div className="page-profile__identity">
            <div className="page-profile__avatar" aria-hidden>
              {initials(u.displayName)}
            </div>
            <div>
              <p className="page-profile__name">{u.displayName}</p>
              <p className="muted page-profile__email">{u.email}</p>
              <p className="page-profile__title">{u.title}</p>
              <p className="muted page-profile__tz">
                Preferred timezone: <strong>{u.timezone}</strong>
              </p>
            </div>
          </div>
        </section>

        <section
          className="panel panel--elevated page-profile__card"
          aria-labelledby="profile-primary-team-heading"
        >
          <h2 id="profile-primary-team-heading" className="panel__h">
            Primary team
          </h2>
          <p className="page-profile__team-name">{u.primaryTeam.name}</p>
          <p className="muted page-profile__team-role">Your role: {u.primaryTeam.role}</p>
          <p className="page-profile__team-desc">{u.primaryTeam.description}</p>
          <p className="muted page-profile__hint">
            Initiative context and rosters in the app inherit from{' '}
            <Link to="/meetings">linked projects</Link> on meetings you edit.
          </p>
        </section>
      </div>

      <section className="panel panel--elevated page-profile__access" aria-labelledby="profile-access-heading">
        <h2 id="profile-access-heading" className="panel__h">
          Team access
        </h2>
        <p className="muted page-profile__access-intro">
          Which teams you’re part of and what you can do. (Illustrative — wire to your org model later.)
        </p>
        <div className="table-wrap table-wrap--plain">
          <table className="page-profile__table">
            <thead>
              <tr>
                <th>Team</th>
                <th>Your role</th>
                <th>Access</th>
              </tr>
            </thead>
            <tbody>
              {u.orgTeams.map((row) => (
                <tr key={row.team}>
                  <td>{row.team}</td>
                  <td>{row.role}</td>
                  <td>{row.access}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className="muted page-profile__footer-note">
        Manage integrations in <Link to="/connected-apps">Connected apps</Link>.
      </p>
    </div>
  )
}
