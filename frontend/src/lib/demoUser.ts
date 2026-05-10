/** Demo workspace identity — replace with auth + `/api/me` when you add accounts. */
export const DEMO_USER = {
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
} as const
