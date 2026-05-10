"""
Confluence Cloud REST API — search pages and add comments (documentation updates).
Embedded Confluence MCP client: same JIRA_API_MAIL + JIRA_API_KEY as Jira; wiki base from
JIRA_URL + /wiki or optional CONFLUENCE_URL (see Settings.confluence_wiki_rest_api_base).
"""

from __future__ import annotations

import base64
import html
import re
from typing import Any

import httpx

from app.config import settings


class ConfluenceMCPError(Exception):
    pass


def _cql_escape_string(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _search_phrase_from_query(query: str, *, max_chars: int = 120) -> str:
    """Short alphanumeric phrase for CQL (avoid empty / punctuation-only queries)."""
    blob = " ".join((query or "").strip().split())[:max_chars]
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}", blob)
    if not words:
        return ""
    return " ".join(words[:5])


def _parse_search_results(data: Any, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in (data or {}).get("results") or []:
        if not isinstance(row, dict):
            continue
        content = row.get("content")
        if content is None and row.get("type") == "page":
            content = row
        if not isinstance(content, dict):
            continue
        cid = content.get("id")
        if not cid:
            continue
        title = content.get("title") or row.get("title") or cid
        out.append({"id": str(cid), "title": str(title), "url": _page_url(content), "mock": False})
        if len(out) >= limit:
            break
    return out


def _wiki_root() -> str:
    root = settings.confluence_wiki_root
    if not root:
        raise ConfluenceMCPError(
            "Confluence wiki URL missing: set JIRA_URL (site root) or CONFLUENCE_URL (…/wiki)"
        )
    return root.rstrip("/")


def _wiki_api() -> str:
    base = settings.confluence_wiki_rest_api_base
    if not base:
        raise ConfluenceMCPError(
            "Confluence REST base missing: set JIRA_URL or CONFLUENCE_URL per backend/.env.example"
        )
    return base.rstrip("/")


def _wiki_api_v2() -> str:
    base = settings.confluence_wiki_api_v2_base
    if not base:
        raise ConfluenceMCPError(
            "Confluence REST v2 base missing: set JIRA_URL or CONFLUENCE_URL per backend/.env.example"
        )
    return base.rstrip("/")


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
    root = settings.confluence_wiki_root or ""
    if not links:
        return root or "https://www.atlassian.com/software/confluence"
    if links.startswith("http"):
        return links
    if not root:
        return links
    return root + (links if links.startswith("/") else "/" + links)


class ConfluenceMCP:
    def __init__(self) -> None:
        self.mode = settings.mcp_mode

    @property
    def is_live(self) -> bool:
        return self.mode == "live" and settings.jira_configured

    async def _request(
        self,
        method: str,
        path: str,
        *,
        api_base: str | None = None,
        json_data: dict | None = None,
        params: dict | None = None,
    ) -> Any:
        if not self.is_live:
            raise ConfluenceMCPError("Confluence MCP is in mock mode or Atlassian credentials missing")
        base = (api_base or _wiki_api()).rstrip("/")
        url = base + (path if path.startswith("/") else "/" + path)
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
                    wiki_base = base
                    raise ConfluenceMCPError(
                        "Confluence API 401 (unauthorized). Atlassian returned an HTML page instead of JSON — "
                        "usually wrong or expired credentials, or a bad wiki base URL. "
                        "Use JIRA_URL=https://YOUR_SITE.atlassian.net (site root only) and optionally "
                        "CONFLUENCE_URL=https://YOUR_SITE.atlassian.net/wiki; same JIRA_API_MAIL + JIRA_API_KEY. "
                        f"Tried REST base: {wiki_base}. "
                        'See README → "Approvals, Notion recap, and Atlassian errors" → '
                        '"Confluence errors on approval".'
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
                    "url": f"{_wiki_root()}",
                    "mock": True,
                }
            ]

        lim = min(max(limit, 1), 25)
        phrase = _search_phrase_from_query(query)
        sk = (settings.confluence_space_key or "").strip()
        sk_esc = _cql_escape_string(sk) if sk else ""

        # Prefer title-based CQL: full-text `text ~` often hits XP-Search / aggregator 400s on Cloud.
        attempts: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add(cql: str, path: str) -> None:
            key = (cql, path)
            if key not in seen:
                seen.add(key)
                attempts.append(key)

        if phrase:
            p = _cql_escape_string(phrase)
            title_q = f'type = page AND title ~ "{p}"'
            if sk:
                add(title_q + f' AND space = "{sk_esc}"', "/content/search")
                add(title_q + f' AND space = "{sk_esc}"', "/search")
            add(title_q, "/content/search")
            add(title_q, "/search")

        if sk:
            recent = f'type = page AND space = "{sk_esc}" order by lastModified desc'
            add(recent, "/content/search")
            add(recent, "/search")

        if phrase:
            p2 = _cql_escape_string(phrase)
            add(f'type = page AND text ~ "{p2}"', "/content/search")
            add(f'type = page AND text ~ "{p2}"', "/search")

        last_err: ConfluenceMCPError | None = None
        any_ok = False
        for cql, path in attempts:
            try:
                data = await self._request("GET", path, params={"cql": cql, "limit": lim})
                any_ok = True
                pages = _parse_search_results(data, lim)
                if pages:
                    return pages
            except ConfluenceMCPError as e:
                last_err = e
                msg = str(e)
                if " 400" in msg or " 404" in msg or "400:" in msg or "404:" in msg:
                    continue
                raise

        # No CQL path worked: list pages in a space (avoids search aggregator when CONFLUENCE_SPACE_KEY is set)
        if sk:
            try:
                data = await self._request(
                    "GET",
                    "/content",
                    params={"type": "page", "spaceKey": sk, "limit": lim},
                )
                any_ok = True
                pages = _parse_search_results(data, lim)
                if pages:
                    return pages
            except ConfluenceMCPError as e:
                last_err = e

        if last_err is not None and not any_ok:
            raise last_err
        return []

    async def add_page_comment(self, page_id: str, body_text: str) -> dict[str, Any]:
        if not self.is_live:
            return {"page_id": page_id, "mock": True}
        safe = html.escape(body_text or "")
        storage = "<p>" + safe.replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"
        # Confluence Cloud: v1 POST .../content/{id}/child/comment often returns 405; v2 footer-comments is supported.
        payload_v2 = {
            "pageId": page_id,
            "body": {"representation": "storage", "value": storage},
        }
        payload_v1 = {
            "type": "comment",
            "container": {"id": page_id, "type": "page", "status": "current"},
            "body": {"storage": {"value": storage, "representation": "storage"}},
        }
        v2_base = _wiki_api_v2()
        try:
            await self._request("POST", "/footer-comments", api_base=v2_base, json_data=payload_v2)
        except ConfluenceMCPError as e:
            msg = str(e)
            # v1 child/comment is deprecated/disallowed on many Cloud sites (405); only fallback when v2 is missing
            if " 404" not in msg:
                raise
            await self._request("POST", f"/content/{page_id}/child/comment", json_data=payload_v1)
        return {"page_id": page_id, "mock": False}


confluence_mcp = ConfluenceMCP()
