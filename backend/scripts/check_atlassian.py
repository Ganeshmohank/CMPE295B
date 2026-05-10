#!/usr/bin/env python3
"""
Verify Atlassian Cloud credentials from backend/.env (JIRA_URL, JIRA_API_MAIL, JIRA_API_KEY).

Optional CONFLUENCE_URL (wiki root) overrides the Confluence probe URL; backend ConfluenceMCP uses the same.

Run from the backend directory:
  python scripts/check_atlassian.py

Exit 0 only if both Jira and Confluence identity endpoints return JSON (200).
"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

# Ensure `app` package resolves when run as `python scripts/check_atlassian.py`
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _basic_header(mail: str, token: str) -> dict[str, str]:
    b64 = base64.b64encode(f"{mail}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {b64}",
        "Accept": "application/json",
    }


async def _probe(name: str, url: str, headers: dict[str, str]) -> bool:
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers=headers)
    ct = (r.headers.get("content-type") or "").lower()
    is_json = "json" in ct or (r.text and r.text.lstrip().startswith("{"))
    preview = (r.text or "")[:200].replace("\n", " ")
    print(f"  {name}: HTTP {r.status_code}  content-type={r.headers.get('content-type', '—')!r}")
    if r.status_code == 200 and is_json:
        print("    OK (JSON)")
        return True
    print(f"    Body preview: {preview!r}")
    return False


async def main() -> int:
    from app.config import settings

    base = (settings.jira_url or "").strip()
    mail = (settings.jira_api_mail or "").strip()
    token = (settings.jira_api_key or "").strip()

    print("Loaded from .env (after normalization):")
    print(f"  JIRA_URL:        {base or '(missing)'}")
    cw = settings.confluence_url
    print(f"  CONFLUENCE_URL:  {cw or '(derived: JIRA_URL + /wiki)'}")
    print(f"  Wiki REST base:  {settings.confluence_wiki_rest_api_base or '(missing)'}")
    print(f"  JIRA_API_MAIL:   {mail or '(missing)'}")
    print(f"  JIRA_API_KEY:    {'(set)' if token else '(missing)'}")
    print(f"  MCP_MODE:        {settings.mcp_mode!r}")

    if not base or not mail or not token:
        print("\nConfigure JIRA_URL, JIRA_API_MAIL, and JIRA_API_KEY in backend/.env")
        return 1

    api_base = settings.confluence_wiki_rest_api_base
    if not api_base:
        print("\nCannot derive Confluence REST base (set JIRA_URL or CONFLUENCE_URL).")
        return 1

    headers = _basic_header(mail, token)
    jira_url = f"{base.rstrip('/')}/rest/api/3/myself"
    conf_url = f"{api_base.rstrip('/')}/user/current"

    print("\nProbing Atlassian (same token for Jira + embedded Confluence MCP / REST):")
    ok_j = await _probe("Jira REST", jira_url, headers)
    ok_c = await _probe("Confluence wiki REST", conf_url, headers)

    if ok_j and ok_c:
        print("\nBoth probes succeeded — credentials and URLs look correct for live MCP (Jira + Confluence).")
        return 0

    print("\nOne or both probes failed.")
    print("  • If Jira OK but Confluence fails: your user may lack Confluence, or Confluence is not on this Cloud site.")
    print("  • If both fail with HTML / 401: wrong site URL, email, or API token (create a new token at id.atlassian.com).")
    print("  • JIRA_URL must be the Cloud site root: https://YOURSITE.atlassian.net")
    print("  • Optional CONFLUENCE_URL=https://YOURSITE.atlassian.net/wiki (explicit wiki root; same as default if omitted)")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
