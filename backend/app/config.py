from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "meeting_intelligence"
    api_prefix: str = "/api"
    # Comma-separated browser origins (production: add https://your-app.vercel.app)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Optional regex, e.g. https://.*\.vercel\.app for all preview deployments
    cors_origin_regex: str | None = None

    # OpenAI Configuration (for action item classification)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Notion MCP Configuration
    notion_api_key: str | None = None  # Internal Integration Token (secret_xxx)
    notion_database_id: str | None = None  # Database ID for tickets/stories
    notion_epics_database_id: str | None = None  # Optional: separate database for epics

    # Jira / Atlassian Cloud (REST API v3)
    jira_url: str | None = None  # https://your-site.atlassian.net (no trailing slash)
    jira_api_mail: str | None = None  # Atlassian account email
    jira_api_key: str | None = None  # API token from id.atlassian.com
    jira_project_key: str | None = None  # e.g. SCRUM — default project for new issues
    # Issue type name when classifier says "task" / generic (must exist in project)
    jira_default_issue_type: str = "Task"
    # Optional Confluence CQL filter: space key to prefer when searching pages
    confluence_space_key: str | None = None

    # Optional: parent Notion page ID for post-meeting recap notes (share page with integration)
    notion_meeting_notes_parent_id: str | None = None
    # When True, station-alpha can POST /meetings/{id}/notion-recap after processing
    notion_post_recap_after_processing: bool = True
    # Optional shared secret for internal callbacks (X-Internal-Secret)
    internal_api_secret: str | None = None

    # Google Calendar MCP Configuration
    google_service_account_email: str | None = None  # From service account JSON
    google_private_key: str | None = None  # From service account JSON (the private_key field)
    google_calendar_id: str | None = None  # Calendar ID (or "primary" for main calendar)
    # Workspace only: user email to impersonate (Domain-Wide Delegation required in Admin Console).
    # Without this, Calendar API rejects events that include attendees (403 forbiddenForServiceAccounts).
    google_workspace_delegated_user: str | None = None
    # Personal Gmail / user calendar: OAuth 2.0 (refresh token). When set with client id+secret, this
    # takes precedence over the service account and can send real invites.
    google_oauth_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_CLIENT_ID"),
    )
    google_oauth_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET"),
    )
    google_calendar_refresh_token: str | None = None

    # MCP Mode: "live" for real API calls, "mock" for simulated responses
    mcp_mode: str = "mock"

    # IANA timezone for calendar invites & parsing "tomorrow at 9am" (see APP_TIMEZONE in .env).
    app_timezone: str = "America/Los_Angeles"

    # Optional SMTP for "Notify Participants" (e.g. Gmail app password, SendGrid SMTP)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_from_name: str | None = None
    smtp_use_tls: bool = True

    # Shown in participant emails if set (e.g. https://your-app.example)
    public_app_url: str | None = None

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def notion_configured(self) -> bool:
        return all([self.notion_api_key, self.notion_database_id])

    @property
    def jira_configured(self) -> bool:
        """Auth only — enough for JQL, list projects, read issues."""
        u = (self.jira_url or "").strip()
        return bool(u and self.jira_api_mail and self.jira_api_key)

    @property
    def jira_project_configured(self) -> bool:
        """Ready to create issues in a default project without passing key each time."""
        return self.jira_configured and bool((self.jira_project_key or "").strip())

    @property
    def google_calendar_configured(self) -> bool:
        """Calendar live creds: service account, or OAuth client id + secret + refresh token (.env)."""
        sa = bool(self.google_service_account_email and self.google_private_key)
        rt = (self.google_calendar_refresh_token or "").strip()
        oauth_user = bool(self.google_oauth_client_id and self.google_oauth_client_secret and rt)
        return sa or oauth_user

    @property
    def openai_configured(self) -> bool:
        return self.openai_api_key is not None


settings = Settings()
