"""Related external links: canonical data lives on `projects`; meetings may override."""

from typing import Any


def placeholder_related_links_for_initiative(label: str) -> list[dict[str, str]]:
    """Dummy Atlassian-style URLs until real Jira/Confluence OAuth is wired."""
    root = "https://example.atlassian.net"
    safe = (label or "Initiative").strip()[:80] or "Initiative"
    return [
        {"title": f"Initiative — {safe}", "url": f"{root}/jira/software/projects/DEMO"},
        {"title": "Team space (Confluence)", "url": f"{root}/wiki/spaces/TEAM"},
    ]


def related_links_for_project_name(name: str) -> list[dict[str, str]]:
    """
    Canonical related links for a project/initiative document.
    Seed uses project **name** (e.g. catalog initiative), not meeting title.
    """
    root = "https://example.atlassian.net"
    if name == "Auth hardening program":
        links: list[dict[str, str]] = [
            {"title": "Threat model (Confluence)", "url": f"{root}/wiki/spaces/SEC/pages/threat-model"},
            {"title": "Pen-test tracker (Jira)", "url": f"{root}/browse/PENTEST-12"},
        ]
        for i in range(1, 14):
            links.append(
                {
                    "title": f"AUTH-{2200 + i}: Hardening workstream",
                    "url": f"{root}/browse/AUTH-{2200 + i}",
                }
            )
        return links
    return placeholder_related_links_for_initiative(name)


def normalize_link_dicts(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for x in raw:
        if isinstance(x, dict) and x.get("title") and x.get("url"):
            out.append({"title": str(x["title"]).strip(), "url": str(x["url"]).strip()})
    return out


def effective_related_links(meeting: dict, project: dict | None) -> list[dict[str, str]]:
    """
    Meeting-specific override wins if non-empty; otherwise use linked project's links.
    """
    m_raw = meeting.get("related_links")
    m_links = normalize_link_dicts(m_raw)
    if m_links:
        return m_links
    if project:
        return normalize_link_dicts(project.get("related_links"))
    return []
