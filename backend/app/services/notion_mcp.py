"""
Notion MCP Client - Real integration with Notion API for ticket/story management.

Supports:
- Create tickets/stories
- Update ticket status, priority, assignee
- Link tickets to epics
- Query and search tickets
- Works in both 'live' and 'mock' modes
"""

import httpx
from datetime import datetime
from typing import Any

from app.config import settings


def _notion_text_chunks(content: str, max_len: int = 1900) -> list[str]:
    """Notion rich_text content is limited per text object."""
    content = (content or "").strip()
    if not content:
        return []
    if len(content) <= max_len:
        return [content]
    return [content[i : i + max_len] for i in range(0, len(content), max_len)]


def _paragraph_blocks_for_text(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        for chunk in _notion_text_chunks(para):
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}],
                    },
                }
            )
    return blocks


def _heading_3_block(title: str) -> dict[str, Any]:
    t = (title or "").strip()[:1900]
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {"content": t}}]},
    }


class NotionMCPError(Exception):
    """Custom exception for Notion MCP errors."""
    pass


def _dashed_notion_uuid(raw: str) -> str:
    """Normalize 32 hex chars (with or without hyphens) to canonical 8-4-4-4-12."""
    s = (raw or "").strip().replace("-", "")
    if len(s) != 32:
        raise NotionMCPError("Notion id must be 32 hex characters (from a page or database URL)")
    return f"{s[:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"


def _merge_callout_snippets(source_snippet: str | None, meeting_title: str | None) -> str | None:
    sn = (source_snippet or "").strip()
    if not sn:
        return None
    if meeting_title and meeting_title.strip():
        return f"[{meeting_title.strip()}] {sn}"
    return sn


class NotionMCP:
    """Notion MCP client for ticket/story management."""

    BASE_URL = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"

    def __init__(self):
        self.api_key = settings.notion_api_key
        self.database_id = settings.notion_database_id
        self.epics_database_id = settings.notion_epics_database_id
        self.mode = settings.mcp_mode

    @property
    def is_configured(self) -> bool:
        return settings.notion_configured

    @property
    def is_live(self) -> bool:
        return self.mode == "live" and self.is_configured

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": self.NOTION_VERSION,
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
        *,
        use_recap_credentials: bool = False,
    ) -> dict:
        """Make a request to Notion API."""
        if use_recap_credentials:
            if self.mode != "live" or not (self.api_key or "").strip():
                raise NotionMCPError(
                    "Notion recap requires MCP_MODE=live and NOTION_API_KEY"
                )
        elif not self.is_live:
            raise NotionMCPError("Notion MCP is in mock mode or not configured")

        url = f"{self.BASE_URL}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._headers(),
                json=json_data,
                timeout=30.0,
            )
            if response.status_code >= 400:
                raise NotionMCPError(f"Notion API error: {response.status_code} - {response.text}")
            return response.json()

    async def create_ticket(
        self,
        title: str,
        description: str,
        ticket_type: str = "task",
        priority: str = "medium",
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
    ) -> dict:
        """
        Create a new ticket/story in Notion.
        
        Returns dict with: id, url, title, type, priority, status
        """
        if not self.is_live:
            # Mock mode - return realistic fake data
            mock_id = f"mock-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return {
                "id": mock_id,
                "url": f"https://notion.so/{mock_id.replace('-', '')}",
                "title": title,
                "type": ticket_type,
                "priority": priority,
                "status": status,
                "assignee": assignee,
                "epic_id": epic_id,
                "created_at": datetime.now().isoformat(),
                "mock": True,
            }

        # Build properties for Notion page
        # Map our status to Notion's status options
        status_map = {
            "To Do": "Not started",
            "In Progress": "In progress", 
            "Done": "Done",
        }
        notion_status = status_map.get(status, "Not started")
        
        # Core properties that should always work
        properties: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Status": {"status": {"name": notion_status}},
        }
        
        # Type as rich_text (matches your schema)
        if ticket_type:
            properties["Type"] = {"rich_text": [{"text": {"content": ticket_type.capitalize()}}]}

        children: list[dict[str, Any]] = []
        meta_bits: list[str] = []
        if meeting_title and meeting_title.strip():
            meta_bits.append(f"Meeting: {meeting_title.strip()}")
        if project_theme and str(project_theme).strip():
            meta_bits.append(f"Project / theme: {str(project_theme).strip()}")
        if source_meeting_id and str(source_meeting_id).strip():
            meta_bits.append(f"Source meeting id: {str(source_meeting_id).strip()}")
        if meta_bits:
            line = " · ".join(meta_bits)
            for chunk in _notion_text_chunks(line):
                children.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": chunk}}],
                        },
                    }
                )
            children.append({"object": "block", "type": "divider", "divider": {}})

        if description and description.strip():
            children.append(_heading_3_block("Summary"))
            children.extend(_paragraph_blocks_for_text(description))

        ctx = (ticket_body_context or "").strip()
        if ctx:
            children.append(_heading_3_block("Context"))
            children.extend(_paragraph_blocks_for_text(ctx))

        disc = (ticket_body_discussion or "").strip()
        if disc:
            children.append(_heading_3_block("Discussion"))
            children.extend(_paragraph_blocks_for_text(disc))

        nxt = (ticket_body_next_steps or "").strip()
        if nxt:
            children.append(_heading_3_block("Next steps"))
            children.extend(_paragraph_blocks_for_text(nxt))

        merged_snippet = _merge_callout_snippets(source_snippet, meeting_title)
        if merged_snippet:
            children.append(_heading_3_block("Transcript"))
            for chunk in _notion_text_chunks(merged_snippet, max_len=1800):
                children.append(
                    {
                        "object": "block",
                        "type": "callout",
                        "callout": {
                            "rich_text": [{"type": "text", "text": {"content": chunk}}],
                            "icon": {"emoji": "📝"},
                        },
                    },
                )

        if len(children) > 100:
            children = children[:100]

        if not children:
            children = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": "(No body text)"}}],
                    },
                }
            ]

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
            "children": children,
        }

        result = await self._request("POST", "/pages", payload)
        
        return {
            "id": result["id"],
            "url": result["url"],
            "title": title,
            "type": ticket_type,
            "priority": priority,
            "status": status,
            "assignee": assignee,
            "epic_id": epic_id,
            "created_at": result["created_time"],
            "mock": False,
        }

    @property
    def recap_live(self) -> bool:
        """
        Meeting recap: MCP live + API key + a parent **page** and/or **database** id.
        If NOTION_MEETING_NOTES_PARENT_ID is unset, NOTION_DATABASE_ID is used (new row in that DB).
        """
        if self.mode != "live" or not (settings.notion_api_key or "").strip():
            return False
        p = (settings.notion_meeting_notes_parent_id or "").strip().replace("-", "")
        d = (settings.notion_database_id or "").strip().replace("-", "")
        return len(p) == 32 or len(d) == 32

    async def _database_title_property_name(self, database_id_dashed: str) -> str:
        data = await self._request(
            "GET", f"/databases/{database_id_dashed}", use_recap_credentials=True
        )
        for name, meta in (data.get("properties") or {}).items():
            if meta.get("type") == "title":
                return name
        raise NotionMCPError(
            "Notion database has no title property; use a database with a title column or set "
            "NOTION_MEETING_NOTES_PARENT_ID to a page instead."
        )

    async def create_meeting_recap_page(
        self,
        *,
        page_title: str,
        section_heading_to_paragraphs: list[tuple[str, str]],
        bullet_sections: list[tuple[str, list[str]]] | None = None,
    ) -> dict[str, Any]:
        """
        Create a recap as a child **page** (NOTION_MEETING_NOTES_PARENT_ID) or a new **row**
        in NOTION_DATABASE_ID when the parent page is not set.
        """
        if not self.recap_live:
            mid = f"mock-recap-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            return {
                "id": mid,
                "url": f"https://notion.so/{mid.replace('-', '')}",
                "mock": True,
            }

        parent_raw = (settings.notion_meeting_notes_parent_id or "").strip().replace("-", "")
        db_raw = (settings.notion_database_id or "").strip().replace("-", "")
        use_page = len(parent_raw) == 32
        use_db = not use_page and len(db_raw) == 32
        if not use_page and not use_db:
            raise NotionMCPError(
                "Set NOTION_MEETING_NOTES_PARENT_ID (page) or NOTION_DATABASE_ID (database), "
                "each shared with the Notion integration"
            )

        children: list[dict[str, Any]] = []
        for heading, body in section_heading_to_paragraphs:
            children.append(_heading_3_block(heading))
            children.extend(_paragraph_blocks_for_text(body))

        if bullet_sections:
            for heading, items in bullet_sections:
                children.append(_heading_3_block(heading))
                for line in items[:60]:
                    line = (line or "").strip()[:1900]
                    if not line:
                        continue
                    children.append(
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": [{"type": "text", "text": {"content": line}}],
                            },
                        }
                    )

        if len(children) > 100:
            children = children[:100]

        title_content = (page_title or "Meeting notes")[:2000]
        fallback_children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": "(No content)"}}],
                },
            }
        ]
        block_children = children if children else fallback_children

        if use_page:
            parent_id = _dashed_notion_uuid(parent_raw)
            payload: dict[str, Any] = {
                "parent": {"page_id": parent_id},
                "properties": {
                    "title": {
                        "title": [{"text": {"content": title_content}}],
                    },
                },
                "children": block_children,
            }
        else:
            database_id = _dashed_notion_uuid(db_raw)
            title_prop = await self._database_title_property_name(database_id)
            payload = {
                "parent": {"database_id": database_id},
                "properties": {
                    title_prop: {
                        "title": [{"text": {"content": title_content}}],
                    },
                },
                "children": block_children,
            }

        result = await self._request("POST", "/pages", payload, use_recap_credentials=True)
        return {
            "id": result["id"],
            "url": result.get("url", ""),
            "mock": False,
        }

    async def update_ticket(
        self,
        ticket_id: str,
        title: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        epic_id: str | None = None,
    ) -> dict:
        """Update an existing ticket in Notion."""
        if not self.is_live:
            return {
                "id": ticket_id,
                "updated": True,
                "changes": {
                    "title": title,
                    "status": status,
                    "priority": priority,
                    "assignee": assignee,
                    "epic_id": epic_id,
                },
                "mock": True,
            }

        properties: dict[str, Any] = {}

        status_map = {
            "To Do": "Not started",
            "In Progress": "In progress",
            "Done": "Done",
        }

        if title:
            properties["Name"] = {"title": [{"text": {"content": title}}]}
        if status:
            notion_status = status_map.get(status, status)
            properties["Status"] = {"status": {"name": notion_status}}

        if not properties:
            return {"id": ticket_id, "updated": False, "message": "No changes provided"}

        result = await self._request("PATCH", f"/pages/{ticket_id}", {"properties": properties})

        return {
            "id": result["id"],
            "url": result["url"],
            "updated": True,
            "mock": False,
        }

    async def get_ticket(self, ticket_id: str) -> dict:
        """Get a ticket by ID."""
        if not self.is_live:
            return {
                "id": ticket_id,
                "title": "Mock Ticket",
                "status": "In Progress",
                "priority": "Medium",
                "mock": True,
            }

        result = await self._request("GET", f"/pages/{ticket_id}")
        props = result.get("properties", {})

        return {
            "id": result["id"],
            "url": result["url"],
            "title": self._extract_title(props.get("Name", {})),
            "status": self._extract_status(props.get("Status", {})),
            "priority": self._extract_select(props.get("priority", {})),
            "type": self._extract_select(props.get("Type", {})),
            "mock": False,
        }

    async def list_epics(self) -> list[dict]:
        """List available epics for linking."""
        if not self.is_live or not self.epics_database_id:
            return [
                {"id": "mock-epic-1", "title": "Q2 Platform Improvements", "mock": True},
                {"id": "mock-epic-2", "title": "Security Hardening", "mock": True},
                {"id": "mock-epic-3", "title": "Performance Optimization", "mock": True},
            ]

        payload = {
            "filter": {
                "property": "Status",
                "select": {"does_not_equal": "Done"}
            },
            "sorts": [{"property": "Name", "direction": "ascending"}]
        }

        result = await self._request("POST", f"/databases/{self.epics_database_id}/query", payload)

        epics = []
        for page in result.get("results", []):
            props = page.get("properties", {})
            epics.append({
                "id": page["id"],
                "title": self._extract_title(props.get("Name", {})),
                "mock": False,
            })
        return epics

    async def find_epic_by_name(self, name: str) -> dict | None:
        """Find an epic by name (fuzzy match)."""
        epics = await self.list_epics()
        name_lower = name.lower()
        
        for epic in epics:
            if name_lower in epic["title"].lower():
                return epic
        return None

    async def search_tickets_by_name(self, name: str) -> list[dict]:
        """
        Search for tickets by name (fuzzy match).
        Returns matching tickets sorted by relevance.
        """
        if not self.is_live:
            # Mock mode - return realistic fake data
            return [
                {
                    "id": f"mock-{name.replace(' ', '-')[:20]}",
                    "url": f"https://notion.so/mock-ticket",
                    "title": name,
                    "status": "In progress",
                    "mock": True,
                }
            ]

        # Query all non-done tickets and filter by name
        payload: dict[str, Any] = {
            "page_size": 100,
            "filter": {
                "property": "Status",
                "status": {"does_not_equal": "Done"}
            }
        }

        result = await self._request("POST", f"/databases/{self.database_id}/query", payload)

        name_lower = name.lower()
        matches = []
        
        for page in result.get("results", []):
            props = page.get("properties", {})
            title = self._extract_title(props.get("Name", {}))
            
            # Check if name matches (fuzzy)
            if name_lower in title.lower() or self._fuzzy_match(name_lower, title.lower()):
                matches.append({
                    "id": page["id"],
                    "url": page["url"],
                    "title": title,
                    "status": self._extract_status(props.get("Status", {})),
                    "type": self._extract_select(props.get("Type", {})),
                    "mock": False,
                })

        # Sort by title similarity (exact matches first)
        matches.sort(key=lambda x: (
            0 if x["title"].lower() == name_lower else
            1 if name_lower in x["title"].lower() else
            2
        ))
        
        return matches

    def _fuzzy_match(self, query: str, target: str) -> bool:
        """Simple fuzzy matching - checks if most words from query appear in target."""
        query_words = set(query.split())
        target_words = set(target.split())
        
        if not query_words:
            return False
            
        # Check if at least 60% of query words appear in target
        matching = sum(1 for w in query_words if any(w in tw for tw in target_words))
        return matching / len(query_words) >= 0.6

    async def find_ticket_by_name(self, name: str) -> dict | None:
        """Find a single ticket by name (best match)."""
        matches = await self.search_tickets_by_name(name)
        if matches:
            return matches[0]
        
        # If no fuzzy match, try LLM-assisted search
        return await self._llm_assisted_search(name)

    async def _llm_assisted_search(self, query: str) -> dict | None:
        """Use LLM to find best matching ticket when fuzzy match fails."""
        from app.config import settings
        
        if not settings.openai_configured or not self.is_live:
            return None
        
        # Get all non-done tickets
        payload: dict[str, Any] = {
            "page_size": 50,
            "filter": {
                "property": "Status",
                "status": {"does_not_equal": "Done"}
            }
        }
        
        try:
            result = await self._request("POST", f"/databases/{self.database_id}/query", payload)
            
            tickets = []
            for page in result.get("results", []):
                props = page.get("properties", {})
                title = self._extract_title(props.get("Name", {}))
                if title:
                    tickets.append({
                        "id": page["id"],
                        "url": page["url"],
                        "title": title,
                        "status": self._extract_status(props.get("Status", {})),
                    })
            
            if not tickets:
                return None
            
            # Ask LLM to find best match
            ticket_list = "\n".join([f"- {t['title']}" for t in tickets])
            
            prompt = f"""Find the best matching ticket for this query: "{query}"

Available tickets:
{ticket_list}

Respond with ONLY the exact ticket title that best matches, or "NONE" if no good match.
Be lenient - partial matches, abbreviations, and similar meanings should match."""

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.openai_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "max_tokens": 100,
                    },
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()
            
            match_title = data["choices"][0]["message"]["content"].strip()
            
            if match_title == "NONE":
                return None
            
            # Find the matching ticket
            for ticket in tickets:
                if ticket["title"].lower() == match_title.lower():
                    ticket["mock"] = False
                    return ticket
            
            return None
            
        except Exception:
            return None

    async def query_tickets(
        self,
        status: str | None = None,
        priority: str | None = None,
        meeting_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query tickets with filters."""
        if not self.is_live:
            return [
                {
                    "id": "mock-ticket-1",
                    "title": "Update API documentation",
                    "status": status or "To Do",
                    "priority": priority or "Medium",
                    "mock": True,
                }
            ]

        filters = []
        if status:
            filters.append({"property": "Status", "status": {"equals": status}})
        if priority:
            filters.append({"property": "priority", "select": {"equals": priority.capitalize()}})
        if meeting_id:
            filters.append({"property": "Meeting ID", "rich_text": {"contains": meeting_id}})

        payload: dict[str, Any] = {"page_size": limit}
        if filters:
            payload["filter"] = {"and": filters} if len(filters) > 1 else filters[0]

        result = await self._request("POST", f"/databases/{self.database_id}/query", payload)

        tickets = []
        for page in result.get("results", []):
            props = page.get("properties", {})
            tickets.append({
                "id": page["id"],
                "url": page["url"],
                "title": self._extract_title(props.get("Name", {})),
                "status": self._extract_status(props.get("Status", {})),
                "priority": self._extract_select(props.get("priority", {})),
                "type": self._extract_select(props.get("Type", {})),
                "mock": False,
            })
        return tickets

    async def add_comment(self, ticket_id: str, comment: str) -> dict:
        """Add a comment to a ticket."""
        if not self.is_live:
            return {
                "id": f"mock-comment-{datetime.now().strftime('%H%M%S')}",
                "ticket_id": ticket_id,
                "comment": comment,
                "mock": True,
            }

        payload = {
            "parent": {"page_id": ticket_id},
            "rich_text": [{"type": "text", "text": {"content": comment}}]
        }

        result = await self._request("POST", "/comments", payload)
        return {
            "id": result["id"],
            "ticket_id": ticket_id,
            "comment": comment,
            "mock": False,
        }

    # Helper methods for extracting Notion property values
    def _extract_title(self, prop: dict) -> str:
        title_list = prop.get("title", [])
        if title_list:
            return title_list[0].get("text", {}).get("content", "")
        return ""

    def _extract_select(self, prop: dict) -> str:
        select = prop.get("select")
        if select:
            return select.get("name", "")
        return ""

    def _extract_status(self, prop: dict) -> str:
        status = prop.get("status")
        if status:
            return status.get("name", "")
        return ""

    def _extract_rich_text(self, prop: dict) -> str:
        rich_text = prop.get("rich_text", [])
        if rich_text:
            return rich_text[0].get("text", {}).get("content", "")
        return ""


# Singleton instance
notion_mcp = NotionMCP()
