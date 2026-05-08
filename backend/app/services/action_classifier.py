"""
LLM-based Action Item Classifier

Uses OpenAI to classify action items and determine:
- Ticket type (story, task, bug, documentation, etc.)
- Recommended orchestration actions
- Priority suggestion
- Epic/project association
"""

import json
import re
from enum import Enum

import httpx

from app.config import settings


class TicketType(str, Enum):
    STORY = "story"
    TASK = "task"
    BUG = "bug"
    DOCUMENTATION = "documentation"
    RESEARCH = "research"
    IMPROVEMENT = "improvement"
    MEETING_FOLLOWUP = "meeting_followup"


class OrchestrationAction(str, Enum):
    CREATE_TICKET = "create_ticket"
    UPDATE_TICKET = "update_ticket"  # Update existing ticket
    UPDATE_DOCUMENTATION = "update_documentation"
    LINK_TO_EPIC = "link_to_epic"
    CREATE_SUBTASK = "create_subtask"
    SCHEDULE_MEETING = "schedule_meeting"  # Actually create calendar event
    CREATE_CALENDAR_EVENT = "create_calendar_event"  # Create calendar invite
    NOTIFY_TEAM = "notify_team"
    NO_ACTION = "no_action"


class ActionClassification:
    """Result of action item classification."""

    def __init__(
        self,
        ticket_type: TicketType,
        recommended_actions: list[OrchestrationAction],
        priority: str,
        suggested_epic: str | None,
        reasoning: str,
        confidence: float,
        target_ticket_name: str | None = None,  # For updates: the ticket to find
        new_status: str | None = None,  # For updates: the new status
        # Extracted fields for ticket creation
        extracted_title: str | None = None,  # Clean, concise title
        extracted_description: str | None = None,  # Detailed description
        story_points: int | None = None,  # Story points if mentioned
        assignee: str | None = None,  # Assignee if mentioned
        labels: list[str] | None = None,  # Tags/labels
        doc_search_term: str | None = None,  # For doc updates: search term
        calendar_time: str | None = None,  # For calendar events: time mentioned
        # Rich ticket body (Notion) — from transcript + meeting context
        ticket_body_context: str | None = None,
        ticket_body_discussion: str | None = None,
        ticket_body_next_steps: str | None = None,
    ):
        self.ticket_type = ticket_type
        self.recommended_actions = recommended_actions
        self.priority = priority
        self.suggested_epic = suggested_epic
        self.reasoning = reasoning
        self.confidence = confidence
        self.target_ticket_name = target_ticket_name
        self.new_status = new_status
        self.extracted_title = extracted_title
        self.extracted_description = extracted_description
        self.story_points = story_points
        self.assignee = assignee
        self.labels = labels or []
        self.doc_search_term = doc_search_term
        self.calendar_time = calendar_time
        self.ticket_body_context = ticket_body_context
        self.ticket_body_discussion = ticket_body_discussion
        self.ticket_body_next_steps = ticket_body_next_steps

    def to_dict(self) -> dict:
        return {
            "ticket_type": self.ticket_type.value,
            "recommended_actions": [a.value for a in self.recommended_actions],
            "priority": self.priority,
            "suggested_epic": self.suggested_epic,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "target_ticket_name": self.target_ticket_name,
            "new_status": self.new_status,
            "extracted_title": self.extracted_title,
            "extracted_description": self.extracted_description,
            "story_points": self.story_points,
            "assignee": self.assignee,
            "labels": self.labels,
            "doc_search_term": self.doc_search_term,
            "calendar_time": self.calendar_time,
            "ticket_body_context": self.ticket_body_context,
            "ticket_body_discussion": self.ticket_body_discussion,
            "ticket_body_next_steps": self.ticket_body_next_steps,
        }


CLASSIFICATION_PROMPT = """You are an expert at classifying action items from meeting transcripts.

Your job is to determine the RIGHT ACTION - not everything needs a ticket!

## CRITICAL: Determine the Intent First
- Is this about SCHEDULING A MEETING or SENDING INVITES? → create_calendar_event
- Is this about CREATING something new (task/bug/story)? → create_ticket
- Is this about UPDATING something existing? → update_ticket  
- Is this about UPDATING DOCUMENTATION? → update_documentation
- Is this just informational/discussion? → no_action

## When to use each action:
- **create_calendar_event**: When the action involves scheduling, sending invites, or setting up a meeting. Look for: "schedule", "send invite", "book a meeting", "set up a call", "calendar", "at X AM/PM"
- **create_ticket**: For genuinely NEW work items (features, bugs, tasks to track)
- **update_ticket**: When referring to an EXISTING ticket/story
- **update_documentation**: When docs need updating
- **no_action**: For discussion items, FYIs, or things that don't need tracking

## IMPORTANT: Calendar vs Ticket
If the action item mentions ANY of these, use create_calendar_event:
- "schedule a meeting"
- "send an invite" / "send invites"
- "book a call"
- "set up a sync"
- "at 9 AM" / "at 3 PM" / specific times
- "tomorrow at" / "next week"
- "calendar invite"

## Examples:

Input: "Schedule director sign-off meeting tomorrow and send an invite at 9 AM PST"
→ recommended_actions: ["create_calendar_event"]
→ extracted_title: "Director sign-off meeting"
→ calendar_time: "9 AM PST tomorrow"
→ reasoning: "This requires sending a calendar invite"

Input: "Send invites for the quarterly review next Tuesday at 2 PM"
→ recommended_actions: ["create_calendar_event"]
→ extracted_title: "Quarterly review"
→ calendar_time: "2 PM next Tuesday"

Input: "Create a story for the checkout latency fix, 3 points"
→ recommended_actions: ["create_ticket"]
→ extracted_title: "Checkout latency fix"
→ story_points: 3

Input: "Update the API documentation"
→ recommended_actions: ["update_documentation"]
→ doc_search_term: "API documentation"

Input: "Mark the auth migration as done"
→ recommended_actions: ["update_ticket"]
→ target_ticket_name: "auth migration"
→ new_status: "Done"

Input: "Discuss the roadmap in next week's meeting"
→ recommended_actions: ["no_action"]
→ reasoning: "Discussion item, not actionable"

Respond with valid JSON only:
{
  "ticket_type": "task",
  "recommended_actions": ["create_ticket"],
  "priority": "medium",
  "suggested_epic": null,
  "reasoning": "Why this action was chosen",
  "confidence": 0.9,
  "target_ticket_name": null,
  "new_status": null,
  "extracted_title": "Clean title",
  "extracted_description": "2-4 sentence summary of the work for the ticket Summary section",
  "ticket_body_context": "Optional: how this ties to meeting goals / project theme (1-3 sentences), or null",
  "ticket_body_discussion": "Optional: key discussion, constraints, or decisions from the transcript, or null",
  "ticket_body_next_steps": "Optional: concrete next steps, owners/deadlines if stated (bullets ok), or null",
  "story_points": null,
  "assignee": null,
  "labels": [],
  "doc_search_term": null,
  "calendar_time": "For calendar events: the time mentioned"
}

When recommended_actions includes create_ticket, use the transcript excerpt in Context to fill ticket_body_* when relevant. Use null for any field you cannot justify from the action item + context.
"""


def transcript_excerpt_for_prompt(
    transcript_text: str | None,
    source_snippet: str | None,
    max_chars: int = 4500,
) -> str | None:
    """Prefer a window around source_snippet so the model sees relevant discussion."""
    if not transcript_text or not str(transcript_text).strip():
        return None
    text = str(transcript_text).strip()
    if len(text) <= max_chars:
        return text
    sn = (source_snippet or "").strip()
    if sn:
        idx = text.find(sn)
        if idx >= 0:
            before_budget = min(2000, max_chars // 2)
            after_budget = max_chars - before_budget - len(sn)
            after_budget = max(400, after_budget)
            start = max(0, idx - before_budget)
            end = min(len(text), idx + len(sn) + after_budget)
            chunk = text[start:end]
            if start > 0:
                chunk = "…" + chunk
            if end < len(text):
                chunk = chunk + "…"
            return chunk
    return text[: max_chars - 1] + "…"


def _json_opt_str(value: object | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


async def classify_action_item(
    description: str,
    source_snippet: str | None = None,
    project_theme: str | None = None,
    meeting_title: str | None = None,
    existing_priority: str = "medium",
    transcript_context: str | None = None,
    other_action_items: list[str] | None = None,
    owner_name: str | None = None,
    due_date: str | None = None,
) -> ActionClassification:
    """
    Classify an action item using LLM with full meeting context.
    
    Falls back to rule-based classification if OpenAI is not configured.
    """
    if not settings.openai_configured:
        return _rule_based_classification(description, existing_priority, project_theme)

    try:
        return await _llm_classification(
            description=description,
            source_snippet=source_snippet,
            project_theme=project_theme,
            meeting_title=meeting_title,
            existing_priority=existing_priority,
            transcript_context=transcript_context,
            other_action_items=other_action_items,
            owner_name=owner_name,
            due_date=due_date,
        )
    except Exception as e:
        print(f"LLM classification failed, falling back to rules: {e}")
        return _rule_based_classification(description, existing_priority, project_theme)


async def _llm_classification(
    description: str,
    source_snippet: str | None,
    project_theme: str | None,
    meeting_title: str | None,
    existing_priority: str,
    transcript_context: str | None = None,
    other_action_items: list[str] | None = None,
    owner_name: str | None = None,
    due_date: str | None = None,
) -> ActionClassification:
    """Use OpenAI to classify the action item."""
    
    # Build rich context for LLM
    context_parts = [
        f"Meeting: {meeting_title or 'Unknown'}",
        f"Project/Theme: {project_theme or 'Not specified'}",
        f"Current Priority: {existing_priority}",
    ]
    
    if owner_name:
        context_parts.append(f"Assigned to: {owner_name}")
    if due_date:
        context_parts.append(f"Due date: {due_date}")
    if source_snippet:
        context_parts.append(f"Source transcript (exact quote): {source_snippet}")
    excerpt = transcript_excerpt_for_prompt(transcript_context, source_snippet)
    if excerpt:
        context_parts.append(
            "Transcript excerpt (use for ticket_body_discussion / context / next_steps when create_ticket applies):\n"
            + excerpt
        )
    if other_action_items:
        context_parts.append(
            "Other action items from this meeting: " + "; ".join(other_action_items[:5])
        )

    user_message = f"""Action Item: {description}

Context:
{chr(10).join('- ' + p for p in context_parts)}

Extract clean ticket fields and classify this action item.
- Create a CONCISE title (not the raw text)
- For create_ticket: extracted_description is the Summary; fill ticket_body_* from transcript only when supported by context
- Extract story points if mentioned (e.g., "3 pointer" = 3)
- Extract assignee if mentioned
- Determine the correct ticket type"""

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_model,
                "messages": [
                    {"role": "system", "content": CLASSIFICATION_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.3,
                "max_tokens": 1200,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    
    # Parse JSON from response (handle potential markdown code blocks)
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```json?\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
    
    result = json.loads(content)

    return ActionClassification(
        ticket_type=TicketType(result.get("ticket_type", "task")),
        recommended_actions=[
            OrchestrationAction(a) for a in result.get("recommended_actions", ["create_ticket"])
            if a in [e.value for e in OrchestrationAction]  # Filter invalid actions
        ],
        priority=result.get("priority", existing_priority),
        suggested_epic=result.get("suggested_epic"),
        reasoning=result.get("reasoning", ""),
        confidence=float(result.get("confidence", 0.7)),
        target_ticket_name=result.get("target_ticket_name"),
        new_status=result.get("new_status"),
        extracted_title=result.get("extracted_title"),
        extracted_description=result.get("extracted_description"),
        story_points=result.get("story_points"),
        assignee=result.get("assignee"),
        labels=result.get("labels", []),
        doc_search_term=result.get("doc_search_term"),
        calendar_time=result.get("calendar_time"),
        ticket_body_context=_json_opt_str(result.get("ticket_body_context")),
        ticket_body_discussion=_json_opt_str(result.get("ticket_body_discussion")),
        ticket_body_next_steps=_json_opt_str(result.get("ticket_body_next_steps")),
    )


def _rule_based_classification(
    description: str,
    existing_priority: str,
    project_theme: str | None,
) -> ActionClassification:
    """
    Fallback rule-based classification when LLM is not available.
    Uses keyword matching to determine ticket type and actions.
    """
    desc_lower = description.lower()
    target_ticket_name = None
    new_status = None

    # Check if this is an UPDATE to an existing ticket
    is_update = False
    update_patterns = [
        "update the story", "update story", "update the ticket", "update ticket",
        "mark as done", "mark as complete", "close the", "close ticket",
        "move to done", "set to done", "mark done", "complete the",
    ]
    
    for pattern in update_patterns:
        if pattern in desc_lower:
            is_update = True
            # Try to extract ticket name after the pattern
            idx = desc_lower.find(pattern)
            after = description[idx + len(pattern):].strip()
            # Take everything after pattern until end or common stop words
            for stop in [" and ", " for ", " to ", " by ", " as "]:
                if stop in after.lower():
                    after = after[:after.lower().find(stop)]
            target_ticket_name = after.strip(" .,;:'\"") if after else None
            
            # Detect status change
            if any(kw in desc_lower for kw in ["done", "complete", "close", "finished"]):
                new_status = "Done"
            elif any(kw in desc_lower for kw in ["in progress", "started", "working"]):
                new_status = "In Progress"
            break

    # Determine ticket type by keywords
    ticket_type = TicketType.TASK
    if any(kw in desc_lower for kw in ["bug", "fix", "broken", "error", "issue", "crash"]):
        ticket_type = TicketType.BUG
    elif any(kw in desc_lower for kw in ["doc", "documentation", "wiki", "confluence", "readme", "write up"]):
        ticket_type = TicketType.DOCUMENTATION
    elif any(kw in desc_lower for kw in ["feature", "user", "customer", "implement new", "add new"]):
        ticket_type = TicketType.STORY
    elif any(kw in desc_lower for kw in ["research", "investigate", "explore", "spike", "poc", "prototype"]):
        ticket_type = TicketType.RESEARCH
    elif any(kw in desc_lower for kw in ["improve", "enhance", "optimize", "refactor", "clean up"]):
        ticket_type = TicketType.IMPROVEMENT
    elif any(kw in desc_lower for kw in ["meeting", "schedule", "sync", "discuss", "follow up", "check in"]):
        ticket_type = TicketType.MEETING_FOLLOWUP

    # Determine actions based on type and whether it's an update
    if is_update:
        actions = [OrchestrationAction.UPDATE_TICKET]
        reasoning = f"Rule-based: Detected UPDATE action for existing ticket"
    elif ticket_type == TicketType.DOCUMENTATION:
        actions = [OrchestrationAction.UPDATE_DOCUMENTATION, OrchestrationAction.CREATE_TICKET]
        reasoning = f"Rule-based: Detected as {ticket_type.value}"
    elif ticket_type == TicketType.MEETING_FOLLOWUP:
        actions = [OrchestrationAction.SCHEDULE_MEETING, OrchestrationAction.NOTIFY_TEAM]
        reasoning = f"Rule-based: Detected as {ticket_type.value}"
    else:
        actions = [OrchestrationAction.CREATE_TICKET]
        if project_theme:
            actions.append(OrchestrationAction.LINK_TO_EPIC)
        reasoning = f"Rule-based: Detected as {ticket_type.value}"

    # Adjust priority by keywords
    priority = existing_priority
    if any(kw in desc_lower for kw in ["urgent", "asap", "critical", "blocker", "immediately"]):
        priority = "critical"
    elif any(kw in desc_lower for kw in ["important", "priority", "soon", "this week"]):
        priority = "high"

    return ActionClassification(
        ticket_type=ticket_type,
        recommended_actions=actions,
        priority=priority,
        suggested_epic=project_theme,
        reasoning=reasoning,
        confidence=0.6,
        target_ticket_name=target_ticket_name,
        new_status=new_status,
    )


async def classify_batch(
    items: list[dict],
) -> list[tuple[dict, ActionClassification]]:
    """
    Classify multiple action items.
    
    Each item should have: description, source_snippet, priority
    Returns list of (item, classification) tuples.
    """
    results = []
    for item in items:
        classification = await classify_action_item(
            description=item.get("description", ""),
            source_snippet=item.get("source_snippet"),
            project_theme=item.get("project_theme"),
            meeting_title=item.get("meeting_title"),
            existing_priority=item.get("priority", "medium"),
        )
        results.append((item, classification))
    return results
