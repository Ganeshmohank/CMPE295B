"""
Confluence Cloud REST API — search pages and add comments (documentation updates).
Uses the same Atlassian site and API token as Jira.
"""

from __future__ import annotations

import base64
import html
from typing import Any

import httpx

from app.config import settings


class ConfluenceMCPError(Exception):
    pass


def _site_base() -> str:
    u = (settings.jira_url or "").strip().rstrip("/")
    if not u:
        raise ConfluenceMCPError("JIRA_URL (Atlassian site) is not set")
    return u


def _wiki_api() -> str:
    return f"{_site_base()}/wiki/rest/api"


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


def _page_url(content: dict[str, Any]) -> str:
    links = (content.get("_links") or {}).get("webui") or ""
    if not links:
        return _site_base() + "/wiki"
    if links.startswith("http"):
        return links
    return _site_base() + "/wiki" + (links if links.startswith("/") else "/" + links)


class ConfluenceMCP:
    def __init__(self) -> None:
        self.mode = settings.mcp_mode

    @property
    def is_live(self) -> bool:
        return self.mode == "live" and settings.jira_configured

    async def _request(self, method: str, path: str, *, json_data: dict | None = None, params: dict | None = None) -> Any:
        if not self.is_live:
            raise ConfluenceMCPError("Confluence MCP is in mock mode or Atlassian credentials missing")
        url = _wiki_api() + path
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
                raw = r.text or ""
                snippet = raw[:800]
                if r.status_code == 401 and "<html" in snippet.lower():
                    raise ConfluenceMCPError(
                        "Confluence API 401 (unauthorized). Atlassian returned an HTML page instead of JSON — "
                        "usually wrong or expired credentials. Fix: set JIRA_URL to your Cloud site root "
                        "(https://YOUR_SITE.atlassian.net, no trailing path), JIRA_API_MAIL to the Atlassian "
                        "account email, JIRA_API_KEY to a current API token from id.atlassian.com, and confirm "
                        "that account can access Confluence. See README (Confluence errors on approval)."
                    )
                if "<html" in snippet.lower():
                    snippet = "(HTML error page from Atlassian; check credentials and JIRA_URL.)"
                raise ConfluenceMCPError(f"Confluence API {r.status_code}: {snippet}")
            if r.status_code == 204 or not r.content:
                return None
            return r.json()

    async def search_pages(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        if not self.is_live:
            return [
                {
                    "id": "mock-page",
                    "title": query[:40],
                    "url": f"{_site_base()}/wiki",
                    "mock": True,
                }
            ]
        q = " ".join((query or "").strip().split())[:100]
        esc = q.replace("\\", "\\\\").replace('"', '\\"')
        parts = ['type = page', f'text ~ "{esc}"']
        sk = (settings.confluence_space_key or "").strip()
        if sk:
            parts.append(f'space = "{sk}"')
        cql = " AND ".join(parts)
        data = await self._request("GET", "/search", params={"cql": cql, "limit": limit})
        out: list[dict[str, Any]] = []
        for row in (data or {}).get("results") or []:
            content = row.get("content") or {}
            cid = content.get("id")
            if not cid:
                continue
            title = content.get("title") or row.get("title") or cid
            out.append({"id": str(cid), "title": title, "url": _page_url(content), "mock": False})
        return out

    async def add_page_comment(self, page_id: str, body_text: str) -> dict[str, Any]:
        if not self.is_live:
            return {"page_id": page_id, "mock": True}
        safe = html.escape(body_text or "")
        storage = "<p>" + safe.replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"
        payload = {
            "type": "comment",
            "container": {"id": page_id, "type": "page"},
            "body": {"storage": {"value": storage, "representation": "storage"}},
        }
        await self._request("POST", f"/content/{page_id}/child/comment", json_data=payload)
        return {"page_id": page_id, "mock": False}


confluence_mcp = ConfluenceMCP()
