"""
Google Calendar MCP Client - Create, update, delete calendar events.

Supports:
- Create events with attendees
- Update event details (time, title, description)
- Delete events
- Works in both 'live' and 'mock' modes
"""

import httpx
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.config import settings
from app.services.invite_recipients import filter_deliverable_invite_recipients


def _calendar_iana_timezone() -> str:
    tz = (settings.app_timezone or "UTC").strip()
    return tz if tz else "UTC"


def normalize_event_wall_time(dt: datetime) -> datetime:
    """Interpret naive datetimes in APP_TIMEZONE; normalize aware datetimes to APP_TIMEZONE."""
    tz = ZoneInfo(_calendar_iana_timezone())
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _oauth_refresh_token() -> str | None:
    t = settings.google_calendar_refresh_token
    if t and isinstance(t, str) and t.strip():
        return t.strip()
    return None


class CalendarMCPError(Exception):
    """Custom exception for Calendar MCP errors."""
    pass


def _is_service_account_attendee_forbidden(status_code: int, body: str) -> bool:
    if status_code != 403:
        return False
    return "forbiddenForServiceAccounts" in body or "Service accounts cannot invite" in body


def _append_suggested_attendees(description: str | None, emails: list[str]) -> str:
    base = (description or "").rstrip()
    lines = "\n".join(f"- {e}" for e in emails)
    block = (
        "\n\n---\nSuggested attendees (add in Calendar — for automated email invites use "
        "GOOGLE_CLIENT_ID/SECRET and GOOGLE_CALENDAR_REFRESH_TOKEN in backend .env, or Workspace DWD):\n"
        f"{lines}"
    )
    return (base + block) if base else block.strip()


class CalendarMCP:
    """Google Calendar MCP client."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    CALENDAR_API = "https://www.googleapis.com/calendar/v3"

    def __init__(self):
        self._access_token: str | None = None
        self._token_expires: datetime | None = None

    @property
    def is_configured(self) -> bool:
        return settings.google_calendar_configured

    @property
    def is_live(self) -> bool:
        return settings.mcp_mode == "live" and self.is_configured

    async def _oauth_user_has_token(self) -> bool:
        if not (settings.google_oauth_client_id and settings.google_oauth_client_secret):
            return False
        return _oauth_refresh_token() is not None

    async def _get_access_token(self) -> str:
        if self._access_token and self._token_expires and datetime.now() < self._token_expires:
            return self._access_token

        refresh = _oauth_refresh_token()
        has_oauth_app = bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)
        sa_ready = bool(settings.google_service_account_email and settings.google_private_key)

        # Gmail OAuth: use refresh token whenever present (never touch service account key).
        if has_oauth_app and refresh:
            return await self._get_access_token_user_refresh()

        if has_oauth_app and not refresh:
            if sa_ready:
                return await self._get_access_token_service_account()
            raise CalendarMCPError(
                "Google Calendar: set GOOGLE_CALENDAR_REFRESH_TOKEN in backend .env "
                "(OAuth Playground with Calendar scope, offline access) beside GOOGLE_CLIENT_ID / SECRET."
            )

        if sa_ready:
            return await self._get_access_token_service_account()

        raise CalendarMCPError("Google Calendar credentials not configured")

    async def _get_access_token_user_refresh(self) -> str:
        """Personal / Workspace user OAuth (refresh token) — can send calendar invites."""
        refresh = _oauth_refresh_token()
        if not refresh:
            raise CalendarMCPError("No OAuth refresh token for Google Calendar")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
            )
        if response.status_code != 200:
            raise CalendarMCPError(f"Failed to refresh user OAuth token: {response.text}")
        data = response.json()
        self._access_token = data["access_token"]
        self._token_expires = datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 60)
        return self._access_token

    async def _get_access_token_service_account(self) -> str:
        import jwt
        import time

        now = int(time.time())
        payload: dict[str, str | int] = {
            "iss": settings.google_service_account_email,
            "scope": "https://www.googleapis.com/auth/calendar",
            "aud": self.TOKEN_URL,
            "iat": now,
            "exp": now + 3600,
        }
        if settings.google_workspace_delegated_user:
            payload["sub"] = settings.google_workspace_delegated_user

        private_key = settings.google_private_key.replace("\\n", "\n")
        try:
            signed_jwt = jwt.encode(payload, private_key, algorithm="RS256")
        except Exception as e:
            raise CalendarMCPError(
                f"Invalid GOOGLE_PRIVATE_KEY PEM (service account): {e}. "
                "Fix the key from your JSON, or comment out GOOGLE_SERVICE_ACCOUNT_EMAIL / "
                "GOOGLE_PRIVATE_KEY if you only use Gmail OAuth (CLIENT_ID / SECRET / REFRESH_TOKEN)."
            ) from e

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": signed_jwt,
                },
            )
        if response.status_code != 200:
            raise CalendarMCPError(f"Failed to get access token: {response.text}")

        data = response.json()
        self._access_token = data["access_token"]
        self._token_expires = datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 60)
        return self._access_token

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: str | None = None,
        attendees: list[str] | None = None,
        location: str | None = None,
        meeting_id: str | None = None,
    ) -> dict:
        """
        Create a calendar event.
        
        Args:
            title: Event title
            start_time: Start datetime
            end_time: End datetime
            description: Event description
            attendees: List of email addresses
            location: Event location
            meeting_id: Internal meeting ID for reference
        
        Returns:
            dict with: id, html_link, title, start, end
        """
        if attendees:
            attendees = filter_deliverable_invite_recipients(attendees)
            if not attendees:
                attendees = None

        if not self.is_live:
            mock_id = f"mock-event-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            ae = list(attendees) if attendees else []
            return {
                "id": mock_id,
                "html_link": f"https://calendar.google.com/calendar/event?eid={mock_id}",
                "title": title,
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "attendees": attendees or [],
                "invite_mode": "sent" if ae else "none",
                "planned_attendees": ae,
                "mock": True,
            }

        token = await self._get_access_token()
        calendar_id = settings.google_calendar_id or "primary"

        tz_name = _calendar_iana_timezone()
        start_n = normalize_event_wall_time(start_time)
        end_n = normalize_event_wall_time(end_time)

        event_body: dict[str, Any] = {
            "summary": title,
            "start": {
                "dateTime": start_n.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": tz_name,
            },
            "end": {
                "dateTime": end_n.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": tz_name,
            },
        }

        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]
        if meeting_id:
            event_body["extendedProperties"] = {
                "private": {"meeting_intelligence_id": meeting_id}
            }

        invite_mode = "none"
        attendee_emails = list(attendees) if attendees else []

        async with httpx.AsyncClient() as client:
            send = "all" if attendee_emails else None
            response = await client.post(
                f"{self.CALENDAR_API}/calendars/{calendar_id}/events",
                headers=self._headers(token),
                json=event_body,
                params={"sendUpdates": send} if send else {},
            )

            if (
                response.status_code not in (200, 201)
                and not await self._oauth_user_has_token()
                and _is_service_account_attendee_forbidden(response.status_code, response.text)
            ):
                # Service accounts cannot send invites without Workspace domain-wide delegation.
                retry_body = {k: v for k, v in event_body.items() if k != "attendees"}
                retry_body["description"] = _append_suggested_attendees(
                    event_body.get("description"), attendee_emails
                )
                response = await client.post(
                    f"{self.CALENDAR_API}/calendars/{calendar_id}/events",
                    headers=self._headers(token),
                    json=retry_body,
                    params={},
                )
                invite_mode = "description_only"

            if response.status_code not in (200, 201):
                raise CalendarMCPError(f"Failed to create event: {response.text}")

            if invite_mode != "description_only" and attendee_emails:
                invite_mode = "sent"

            data = response.json()
            return {
                "id": data["id"],
                "html_link": data.get("htmlLink"),
                "title": data.get("summary"),
                "start": data["start"].get("dateTime"),
                "end": data["end"].get("dateTime"),
                "attendees": [a.get("email") for a in data.get("attendees", [])],
                "invite_mode": invite_mode,
                "planned_attendees": attendee_emails,
                "mock": False,
            }

    async def update_event(
        self,
        event_id: str,
        title: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        description: str | None = None,
        attendees: list[str] | None = None,
        location: str | None = None,
    ) -> dict:
        """Update an existing calendar event."""
        if attendees is not None:
            attendees = filter_deliverable_invite_recipients(attendees)

        if not self.is_live:
            return {
                "id": event_id,
                "updated": True,
                "changes": {
                    "title": title,
                    "start_time": start_time.isoformat() if start_time else None,
                    "end_time": end_time.isoformat() if end_time else None,
                    "attendees": attendees,
                },
                "mock": True,
            }

        token = await self._get_access_token()
        calendar_id = settings.google_calendar_id or "primary"

        # First get the existing event
        async with httpx.AsyncClient() as client:
            get_response = await client.get(
                f"{self.CALENDAR_API}/calendars/{calendar_id}/events/{event_id}",
                headers=self._headers(token),
            )
            if get_response.status_code != 200:
                raise CalendarMCPError(f"Event not found: {event_id}")

            event_body = get_response.json()

        # Update fields
        if title:
            event_body["summary"] = title
        if start_time:
            st = normalize_event_wall_time(start_time)
            event_body["start"] = {
                "dateTime": st.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": _calendar_iana_timezone(),
            }
        if end_time:
            et = normalize_event_wall_time(end_time)
            event_body["end"] = {
                "dateTime": et.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": _calendar_iana_timezone(),
            }
        if description is not None:
            event_body["description"] = description
        if location is not None:
            event_body["location"] = location
        if attendees is not None:
            cleaned = filter_deliverable_invite_recipients(attendees)
            event_body["attendees"] = [{"email": email} for email in cleaned]

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.CALENDAR_API}/calendars/{calendar_id}/events/{event_id}",
                headers=self._headers(token),
                json=event_body,
                params={"sendUpdates": "all"},
            )

            if response.status_code != 200:
                raise CalendarMCPError(f"Failed to update event: {response.text}")

            data = response.json()
            return {
                "id": data["id"],
                "html_link": data.get("htmlLink"),
                "updated": True,
                "mock": False,
            }

    async def delete_event(self, event_id: str) -> dict:
        """Delete a calendar event."""
        if not self.is_live:
            return {
                "id": event_id,
                "deleted": True,
                "mock": True,
            }

        token = await self._get_access_token()
        calendar_id = settings.google_calendar_id or "primary"

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.CALENDAR_API}/calendars/{calendar_id}/events/{event_id}",
                headers=self._headers(token),
                params={"sendUpdates": "all"},
            )

            if response.status_code not in (200, 204):
                raise CalendarMCPError(f"Failed to delete event: {response.text}")

            return {
                "id": event_id,
                "deleted": True,
                "mock": False,
            }

    async def get_event(self, event_id: str) -> dict | None:
        """Get a calendar event by ID."""
        if not self.is_live:
            return {
                "id": event_id,
                "title": "Mock Event",
                "start": datetime.now().isoformat(),
                "end": (datetime.now() + timedelta(hours=1)).isoformat(),
                "mock": True,
            }

        token = await self._get_access_token()
        calendar_id = settings.google_calendar_id or "primary"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.CALENDAR_API}/calendars/{calendar_id}/events/{event_id}",
                headers=self._headers(token),
            )

            if response.status_code == 404:
                return None
            if response.status_code != 200:
                raise CalendarMCPError(f"Failed to get event: {response.text}")

            data = response.json()
            return {
                "id": data["id"],
                "html_link": data.get("htmlLink"),
                "title": data.get("summary"),
                "description": data.get("description"),
                "start": data["start"].get("dateTime"),
                "end": data["end"].get("dateTime"),
                "attendees": [a.get("email") for a in data.get("attendees", [])],
                "location": data.get("location"),
                "mock": False,
            }


# Singleton instance
calendar_mcp = CalendarMCP()
