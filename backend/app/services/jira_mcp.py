"""
Jira Cloud REST API client (v3) — work items, search, transitions, comments.

Mirrors the shape returned by Notion MCP where orchestration expects
id, url, title, type, priority, status, mock; Jira uses issue key as id for logs/UI.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime
from typing import Any

import httpx

from app.config import settings


class JiraMCPError(Exception):
    pass


def _site_base() -> str:
    u = (settings.jira_url or "").strip().rstrip("/")
    if not u:
        raise JiraMCPError("JIRA_URL is not set")
    return u


def _api_base() -> str:
    return f"{_site_base()}/rest/api/3"


def _headers() -> dict[str, str]:
    mail = (settings.jira_api_mail or "").strip()
    token = (settings.jira_api_key or "").strip()
    raw = f"{mail}:{token}".encode()
    b64 = base64.b64encode(raw).decode()
    return {
        "Authorization": f"Basic {b64}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _plain_to_adf(text: str) -> dict[str, Any]:
    blocks = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    content: list[dict[str, Any]] = []
    for para in blocks:
        line = para.replace("\n", " ")
        content.append({"type": "paragraph", "content": [{"type": "text", "text": line}]})
    if not content:
        content = [{"type": "paragraph", "content": [{"type": "text", "text": "(No description)"}]}]
    return {"type": "doc", "version": 1, "content": content}


def _priority_name(p: str | None) -> str | None:
    if not p:
        return None
    m = (p or "").strip().lower()
    mapping = {
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "critical": "Highest",
        "highest": "Highest",
    }
    return mapping.get(m, p[:1].upper() + p[1:].lower() if p else None)


def _issue_type_name(ticket_type: str) -> str:
    m = (ticket_type or "task").strip().lower()
    if m in ("story", "feature"):
        return "Story"
    if m in ("bug", "defect"):
        return "Bug"
    if m in ("spike", "task", "subtask"):
        return (settings.jira_default_issue_type or "Task").strip() or "Task"
    return (settings.jira_default_issue_type or "Task").strip() or "Task"


def _jql_literal(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


class JiraMCP:
    def __init__(self) -> None:
        self.mode = settings.mcp_mode

    @property
    def is_configured(self) -> bool:
        return settings.jira_configured and settings.jira_project_configured

    @property
    def is_live(self) -> bool:
        return self.mode == "live" and self.is_configured

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        if not self.is_live:
            raise JiraMCPError("Jira MCP is in mock mode or not configured (missing JIRA_URL / mail / token / project)")
        url = _api_base() + path
        async with httpx.AsyncClient() as client:
            r = await client.request(
                method,
                url,
                headers=_headers(),
                json=json_data,
                params=params,
                timeout=45.0,
            )
            if r.status_code >= 400:
                raise JiraMCPError(f"Jira API {r.status_code}: {r.text[:800]}")

            if r.status_code == 204 or not r.content:
                return None
            return r.json()

    def _browse_url(self, key: str) -> str:
        return f"{_site_base()}/browse/{key}"

    async def create_ticket(
        self,
        title: str,
        description: str,
        ticket_type: str = "task",
        priority: str | None = "medium",
        status: str = "To Do",
        assignee: str | None = None,
        epic_id: str | None = None,
        source_meeting_id: str | None = None,
        source_snippet: str | None = None,
        ticket_body_context: str | None = None,
        ticket_body_discussion: str | None = None,
        ticket_body_next_steps: str | None = None,
        meeting_title: str | None = None,
        project_theme: str | None = None,
    ) -> dict[str, Any]:
        proj = (settings.jira_project_key or "").strip()
        if not self.is_live:
            key = f"{proj}-MOCK"
            return {
                "id": key,
                "key": key,
                "url": self._browse_url(key),
                "title": title,
                "type": _issue_type_name(ticket_type),
                "priority": priority or "medium",
                "status": status,
                "assignee": assignee,
                "epic_id": epic_id,
                "created_at": datetime.now().isoformat(),
                "mock": True,
            }

        body_parts: list[str] = []
        if meeting_title:
            body_parts.append(f"Meeting: {meeting_title}")
        if project_theme:
            body_parts.append(f"Project / theme: {project_theme}")
        if source_meeting_id:
            body_parts.append(f"Source meeting id: {source_meeting_id}")
        if body_parts:
            body_parts.append("")
        body_parts.append(description or "")
        if ticket_body_context:
            body_parts.extend(["", "Context", ticket_body_context])
        if ticket_body_discussion:
            body_parts.extend(["", "Discussion", ticket_body_discussion])
        if ticket_body_next_steps:
            body_parts.extend(["", "Next steps", ticket_body_next_steps])
        if source_snippet:
            sn = source_snippet.strip()
            if meeting_title:
                sn = f"[{meeting_title.strip()}] {sn}"
            body_parts.extend(["", "Transcript", sn])

        full_desc = "\n\n".join(body_parts).strip()
        fields: dict[str, Any] = {
            "project": {"key": proj},
            "summary": (title or "Untitled")[:255],
            "issuetype": {"name": _issue_type_name(ticket_type)},
            "description": _plain_to_adf(full_desc),
        }
        pn = _priority_name(priority)
        if pn:
            fields["priority"] = {"name": pn}

        payload: dict[str, Any] = {"fields": fields}
        # Epic as parent works on many team-managed boards
        if epic_id and str(epic_id).strip():
            ek = str(epic_id).strip().upper()
            if "-" in ek:
                payload["fields"]["parent"] = {"key": ek}

        result = await self._request("POST", "/issue", json_data=payload)
        key = result.get("key") or result.get("id")
        return {
            "id": key,
            "key": key,
            "url": self._browse_url(key),
            "title": title,
            "type": _issue_type_name(ticket_type),
            "priority": priority or "medium",
            "status": status,
            "assignee": assignee,
            "epic_id": epic_id,
            "created_at": datetime.now().isoformat(),
            "mock": False,
        }

    async def _transitions(self, issue_id_or_key: str) -> list[dict]:
        data = await self._request("GET", f"/issue/{issue_id_or_key}/transitions")
        return list((data or {}).get("transitions") or [])

    def _pick_transition_id(self, transitions: list[dict], desired: str) -> str | None:
        d = desired.strip().lower()
        aliases = {
            "to do": ("open", "to do", "backlog", "todo"),
            "in progress": ("in progress", "indeterminate", "doing"),
            "done": ("done", "closed", "complete", "resolved"),
        }
        want = aliases.get(d, (d.replace(" ", ""),))

        for t in transitions:
            to_name = ((t.get("to") or {}).get("name") or "").lower()
            name = (t.get("name") or "").lower()
            for w in want:
                if w in to_name or w in name:
                    return str(t.get("id"))
        for t in transitions:
            to_name = ((t.get("to") or {}).get("name") or "").lower()
            if d in to_name or to_name in d:
                return str(t.get("id"))
        return None

    async def update_ticket(
        self,
        ticket_id: str,
        title: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        epic_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_live:
            return {
                "id": ticket_id,
                "key": ticket_id,
                "url": self._browse_url(ticket_id) if "-" in str(ticket_id) else f"{_site_base()}/browse/x",
                "updated": True,
                "mock": True,
            }

        if title:
            await self._request(
                "PUT",
                f"/issue/{ticket_id}",
                json_data={"fields": {"summary": title[:255]}},
            )

        if priority:
            pn = _priority_name(priority)
            if pn:
                await self._request(
                    "PUT",
                    f"/issue/{ticket_id}",
                    json_data={"fields": {"priority": {"name": pn}}},
                )

        if status:
            transitions = await self._transitions(ticket_id)
            tid = self._pick_transition_id(transitions, status)
            if not tid:
                raise JiraMCPError(
                    f"No Jira transition to match status '{status}'. "
                    f"Available: {[((x.get('to') or {}).get('name')) for x in transitions]}"
                )
            await self._request(
                "POST",
                f"/issue/{ticket_id}/transitions",
                json_data={"transition": {"id": tid}},
            )

        issue = await self._request("GET", f"/issue/{ticket_id}", params={"fields": "summary,status"})
        fields = (issue or {}).get("fields") or {}
        st = ((fields.get("status") or {}).get("name")) or ""
        return {
            "id": (issue or {}).get("key") or ticket_id,
            "key": (issue or {}).get("key") or ticket_id,
            "url": self._browse_url((issue or {}).get("key") or ticket_id),
            "updated": True,
            "status": st,
            "mock": False,
        }

    async def add_comment(self, ticket_id: str, comment: str) -> dict[str, Any]:
        if not self.is_live:
            return {
                "id": f"mock-comment-{datetime.now().strftime('%H%M%S')}",
                "ticket_id": ticket_id,
                "comment": comment,
                "mock": True,
            }

        await self._request(
            "POST",
            f"/issue/{ticket_id}/comment",
            json_data={"body": _plain_to_adf(comment)},
        )
        return {"ticket_id": ticket_id, "comment": comment, "mock": False}

    async def issuetype_name_for_jql_epic(self) -> str:
        return "Epic"

    async def list_epics(self) -> list[dict[str, Any]]:
        if not self.is_live:
            return [
                {"key": "SCRUM-EP1", "id": "SCRUM-EP1", "title": "Q2 Platform", "mock": True},
            ]
        proj = (settings.jira_project_key or "").strip()
        it = await self.issuetype_name_for_jql_epic()
        jql = f'project = {proj} AND issuetype = "{it}" ORDER BY updated DESC'
        issues = await self._search_issues(jql, 50, ["summary", "issuetype"])
        epics: list[dict[str, Any]] = []
        for issue in issues:
            f = issue.get("fields") or {}
            epics.append(
                {
                    "id": issue.get("key"),
                    "key": issue.get("key"),
                    "title": (f.get("summary") or issue.get("key")),
                    "mock": False,
                }
            )
        return epics

    async def find_epic_by_name(self, name: str) -> dict | None:
        epics = await self.list_epics()
        nl = name.lower()
        for epic in epics:
            if nl in epic["title"].lower():
                return epic
        for epic in epics:
            words = set(re.split(r"\W+", nl)) - {""}
            if words and sum(1 for w in words if w in epic["title"].lower()) / len(words) >= 0.5:
                return epic
        return None

    async def _search_issues(self, jql: str, max_results: int, fields: list[str]) -> list[dict]:
        data = await self._request(
            "POST",
            "/search/jql",
            json_data={"jql": jql, "maxResults": max_results, "fields": fields},
        )
        return list((data or {}).get("issues") or [])

    async def search_issues_by_summary(self, name: str, *, not_done: bool = True) -> list[dict[str, Any]]:
        if not self.is_live:
            return [
                {
                    "id": "MOCK-1",
                    "key": "MOCK-1",
                    "url": self._browse_url("MOCK-1"),
                    "title": name,
                    "status": "To Do",
                    "mock": True,
                }
            ]
        proj = (settings.jira_project_key or "").strip()
        term = _jql_literal(name.strip()[:120])
        status_filter = "" if not not_done else " AND statusCategory != Done"
        jql = (
            f'project = {proj}{status_filter} AND (summary ~ "{term}*" OR text ~ "{term}") '
            "ORDER BY updated DESC"
        )
        try:
            issues = await self._search_issues(jql, 25, ["summary", "status", "issuetype"])
        except JiraMCPError:
            issues = []
        if not issues:
            jql2 = f"project = {proj}{status_filter} ORDER BY updated DESC"
            try:
                all_issues = await self._search_issues(jql2, 50, ["summary", "status", "issuetype"])
            except JiraMCPError:
                all_issues = []
            nl = name.lower()
            issues = [
                x
                for x in all_issues
                if nl in ((x.get("fields") or {}).get("summary") or "").lower()
            ]

        out: list[dict[str, Any]] = []
        for issue in issues:
            f = issue.get("fields") or {}
            out.append(
                {
                    "id": issue.get("key"),
                    "key": issue.get("key"),
                    "url": self._browse_url(issue.get("key")),
                    "title": f.get("summary") or issue.get("key"),
                    "status": ((f.get("status") or {}).get("name") or ""),
                    "type": ((f.get("issuetype") or {}).get("name") or ""),
                    "mock": False,
                }
            )
        return out

    async def find_ticket_by_name(self, name: str) -> dict | None:
        matches = await self.search_issues_by_summary(name)
        if matches:
            return matches[0]
        return await self._llm_pick_issue(name, matches)

    async def _llm_pick_issue(self, query: str, _: list) -> dict | None:
        if not settings.openai_configured or not self.is_live:
            return None
        issues = await self._search_issues(
            f"project = {(settings.jira_project_key or '').strip()} AND statusCategory != Done ORDER BY updated DESC",
            40,
            ["summary"],
        )
        tickets: list[dict[str, str]] = []
        for issue in issues:
            f = issue.get("fields") or {}
            sm = f.get("summary")
            if sm:
                tickets.append({"key": issue.get("key"), "title": sm})
        if not tickets:
            return None

        ticket_list = "\n".join([f"- {t['title']} ({t['key']})" for t in tickets])
        prompt = f"""Find the best matching Jira issue for: "{query}"

Issues:
{ticket_list}

Reply with ONLY the issue KEY (e.g. SCRUM-12) or NONE."""

        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 40,
                },
                timeout=20.0,
            )
            r.raise_for_status()
            key = r.json()["choices"][0]["message"]["content"].strip()
        if key.upper() == "NONE":
            return None
        key = key.strip().strip("`").split()[0]
        for t in tickets:
            if t["key"].upper() == key.upper():
                return {
                    "id": t["key"],
                    "key": t["key"],
                    "url": self._browse_url(t["key"]),
                    "title": t["title"],
                    "mock": False,
                }
        return None

    async def link_issue_to_epic(self, issue_key: str, epic_key: str) -> dict[str, Any]:
        """Best-effort: parent link (team-managed) or noop with flag."""
        if not self.is_live:
            return {"linked": True, "mock": True, "issue_key": issue_key, "epic_key": epic_key}
        try:
            await self._request(
                "PUT",
                f"/issue/{issue_key}",
                json_data={"fields": {"parent": {"key": epic_key}}},
            )
            return {"linked": True, "issue_key": issue_key, "epic_key": epic_key, "mock": False}
        except JiraMCPError as e:
            return {"linked": False, "issue_key": issue_key, "epic_key": epic_key, "error": str(e)}


jira_mcp = JiraMCP()
