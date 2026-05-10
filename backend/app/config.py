from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip_optional_quotes(s: str) -> str:
    t = s.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in '"\'':
        t = t[1:-1].strip()
    return t


def _normalize_atlassian_cloud_site_url(url: str | None) -> str | None:
    """Site root only: https://company.atlassian.net (no /wiki, /jira, trailing slash)."""
    if url is None:
        return None
    s = _strip_optional_quotes(url)
    if not s:
        return None
    s = s.rstrip("/")
    low = s.lower()
    for suffix in ("/wiki", "/jira"):
        if low.endswith(suffix):
            s = s[: -len(suffix)].rstrip("/")
            low = s.lower()
    return s or None


def _normalize_confluence_wiki_root_url(raw: str) -> str | None:
    """
    CONFLUENCE_URL → canonical wiki root: https://tenant.atlassian.net/wiki
    Accepts site root or .../wiki; strips deeper paths back to /wiki for Cloud.
    """
    s = _strip_optional_quotes(raw).strip().rstrip("/")
    if not s:
        return None
    p = urlparse(s)
    if not p.scheme or not p.netloc:
        return None
    path = (p.path or "").rstrip("/")
    host = p.netloc.lower()
    base = f"{p.scheme}://{p.netloc}"
    if path == "" or path == "/":
        return f"{base}/wiki"
    low = path.lower()
    if low == "/wiki" or low.startswith("/wiki/"):
        return f"{base}/wiki"
    if "atlassian.net" in host:
        return f"{base}/wiki"
    return f"{base}{path}" if path else f"{base}/wiki"


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
    # Optional Confluence wiki root (overrides JIRA_URL + /wiki for REST + links). Same token as Jira.
    # Example: https://your-site.atlassian.net/wiki
    confluence_url: str | None = None
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

    @field_validator("jira_url", mode="before")
    @classmethod
    def _v_jira_url(cls, v: object) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if not isinstance(v, str):
            return None
        return _normalize_atlassian_cloud_site_url(v)

    @field_validator("jira_api_mail", mode="before")
    @classmethod
    def _v_jira_mail(cls, v: object) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if not isinstance(v, str):
            return None
        return _strip_optional_quotes(v)

    @field_validator("jira_api_key", mode="before")
    @classmethod
    def _v_jira_key(cls, v: object) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if not isinstance(v, str):
            return None
        return _strip_optional_quotes(v)

    @field_validator("confluence_url", mode="before")
    @classmethod
    def _v_confluence_url(cls, v: object) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if not isinstance(v, str):
            return None
        return _normalize_confluence_wiki_root_url(v)

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

    @property
    def confluence_wiki_root(self) -> str | None:
        """Wiki base URL: https://tenant.atlassian.net/wiki (no trailing slash)."""
        if self.confluence_url:
            return self.confluence_url.rstrip("/")
        ju = (self.jira_url or "").strip().rstrip("/")
        return f"{ju}/wiki" if ju else None

    @property
    def confluence_wiki_rest_api_base(self) -> str | None:
        """Confluence Cloud REST v1 base: .../wiki/rest/api"""
        r = self.confluence_wiki_root
        return f"{r}/rest/api" if r else None

    @property
    def confluence_wiki_api_v2_base(self) -> str | None:
        """Confluence Cloud REST v2 base: .../wiki/api/v2 (comments, pages, …)."""
        r = self.confluence_wiki_root
        return f"{r}/api/v2" if r else None


settings = Settings()
