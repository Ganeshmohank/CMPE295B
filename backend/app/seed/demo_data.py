"""
Demo-quality seed data for meeting intelligence dashboard.
Run via: python scripts/seed.py (from backend directory).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from app.db import get_db
from app.domain.enums import (
    ActionItemStatus,
    LogStage,
    LogStatus,
    MeetingStatus,
    Priority,
    ProcessingStatus,
)

POOL: dict[str, tuple[str, str | None]] = {
    "alex": ("Alex Chen", "alex.chen@example.com"),
    "jordan": ("Jordan Lee", "jordan.lee@example.com"),
    "sam": ("Sam Rivera", "sam.rivera@example.com"),
    "taylor": ("Taylor Kim", "taylor.kim@example.com"),
    "morgan": ("Morgan Patel", "morgan.patel@example.com"),
    "riley": ("Riley Brooks", "riley.brooks@example.com"),
    "casey": ("Casey Wu", "casey.wu@example.com"),
    "drew": ("Drew Martinez", "drew.martinez@example.com"),
    "jamie": ("Jamie Singh", "jamie.singh@example.com"),
    "avery": ("Avery Novak", "avery.novak@example.com"),
    "blake": ("Blake Ortiz", "blake.ortiz@example.com"),
    "quinn": ("Quinn Foster", None),
}

# Rich text for meeting detail "context" rail (developer / PM / project lens)
CONTEXT_PRESET: dict[str, dict[str, str]] = {
    "Weekly Engineering Sync": {
        "project_theme": "Platform reliability & rollout freeze",
        "context_developer": "Next: land canary dashboard, profile checkout latency, unblock SSO cert with IT. Post triage notes in #eng-incidents.",
        "context_pm": "Design review deadline for partial refunds doc; align stakeholders on freeze scope and comms.",
    },
    "Product Planning Review": {
        "project_theme": "Q2 roadmap — onboarding vs integrations",
        "context_developer": "Engineering to size activation milestone work; dependency on analytics schema for funnel events.",
        "context_pm": "Prioritize onboarding friction; legal on retention copy blocks enterprise launch narrative.",
    },
    "Client Onboarding Discussion": {
        "project_theme": "Acme enterprise rollout",
        "context_developer": "SSO worksheet + CSV import bug; shadow environment readiness for next Tuesday dry run.",
        "context_pm": "Executive workshop scheduling; success metrics deck for QBR follow-up.",
    },
    "Bug Triage Meeting": {
        "project_theme": "Incident prevention & quality bar",
        "context_developer": "P1 webhook storm hotfix tonight; Safari bisect assigned; staging replica lag masking races.",
        "context_pm": "Customer comms on known issues; prioritize P1/P2 for sprint commitment.",
    },
    "Release Readiness Review": {
        "project_theme": "Release 2.14 go/no-go",
        "context_developer": "Soak test with autoscaling policy; rollback playbook verified; feature flags safe defaults.",
        "context_pm": "Marketing release notes deadline; GA comms aligned with support macros.",
    },
    "Sprint Retrospective": {
        "project_theme": "Team health & process",
        "context_developer": "CI faster; no formal carry-over tasks — watch standup length next sprint.",
        "context_pm": "Celebrate velocity; no customer-facing commitments from this retro.",
    },
    "Incident Postmortem": {
        "project_theme": "Cache stampede / flash sale",
        "context_developer": "Circuit breaker tuning, traffic shaping playbook, game day April 20.",
        "context_pm": "External postmortem summary for largest accounts; SLA review with CS.",
    },
    "API Deprecation Workshop": {
        "project_theme": "v1 sunset (July 1)",
        "context_developer": "SDK linter warnings, migration guide examples, breaking change tests in CI.",
        "context_pm": "Customer email campaign April 15; sales enablement on upgrade talking points.",
    },
    "Design Critique: Checkout Flow": {
        "project_theme": "Checkout UX — progressive disclosure & errors",
        "context_developer": "Recording failed mid-export; recover partial notes from design file comments and Figma version history.",
        "context_pm": "Reschedule critique once full recording available; align with checkout reliability program messaging.",
    },
    "Infrastructure Office Hours": {
        "project_theme": "Platform ops — Kafka, Redis, K8s",
        "context_developer": "Refresh runbook for cluster upgrade; Drew owns docs. Sam opens change ticket for April 6 overnight window.",
        "context_pm": "Communicate maintenance window to internal stakeholders; no customer-facing blast unless scope grows.",
    },
    "QBR — Acme Corp": {
        "project_theme": "Acme QBR & expansion",
        "context_developer": "Pipe revised success metrics into warehouse; validate export jobs before deck final.",
        "context_pm": "Send success metrics deck revision; book executive workshop; confirm support SLAs by April 10.",
    },
    "Security Review: Auth Hardening": {
        "project_theme": "Auth hardening program",
        "context_developer": "Await Zoom finalize; prep threat model appendix and pen-test findings links for the live review.",
        "context_pm": "Stakeholder list for readout; legal/compliance loop on retention of auth audit logs.",
    },
    "Data Pipeline Sync": {
        "project_theme": "Analytics warehouse & dbt reliability",
        "context_developer": "Incremental watermark guard for late-arriving events; unblock warehouse permissions (done).",
        "context_pm": "SLA dashboard in Confluence for exec visibility; dependency on finance close calendar.",
    },
    "Hiring Panel Debrief": {
        "project_theme": "Engineering hiring — systems track",
        "context_developer": "Reference checks and leveling decision; align with hiring manager on loop feedback template.",
        "context_pm": "Comp band refresh with People; no external comms until offer stage.",
    },
    "Customer Support Escalation": {
        "project_theme": "Enterprise bulk export performance",
        "context_developer": "Profile hot path; flame graphs by Thursday. Workaround steps to CS today.",
        "context_pm": "Customer communication if SLA at risk; CS lead as single voice to Acme champion.",
    },
    "Mobile Beta Feedback Session": {
        "project_theme": "Mobile beta — stability & notifications",
        "context_developer": "Tickets for low-memory crash and duplicate pushes; coordinate April 5 beta build with release.",
        "context_pm": "Beta cohort NPS pulse; app store copy review if crash rate improves.",
    },
    "Cross-team Dependencies Forum": {
        "project_theme": "Payments ↔ fraud rules API",
        "context_developer": "Blake unblocks schema review; payments unblocked on contract tests once schema merges.",
        "context_pm": "Exec summary if slip risks Q2 commitments; no new customer promises from this forum.",
    },
    "UX Research Readout": {
        "project_theme": "Search discoverability",
        "context_developer": "Taylor prototypes filter quick wins; Avery aligns design tokens with design system next sprint.",
        "context_pm": "Research replay for PMM; prioritize one ship candidate for roadmap draft.",
    },
    "Compliance Training Dry Run": {
        "project_theme": "SOC2 evidence & training",
        "context_developer": "Assign owners offline for evidence workstreams; attach runbook links to compliance workspace.",
        "context_pm": "Timeline for auditor packet; training attendance tracking for HR.",
    },
    "Vendor Evaluation — Transcription Tooling": {
        "project_theme": "Transcription vendor strategy",
        "context_developer": "Pilot config for EMEA secondary vendor; API keys and data residency checklist.",
        "context_pm": "Riley pilot kickoff April 9; Morgan cost projections to finance; contract redlines with legal.",
    },
}


def _utc(*, days_ago: int = 0, hour: int = 15, minute: int = 0) -> datetime:
    base = datetime.now(timezone.utc).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base - timedelta(days=days_ago)


def _seg(speaker: str, text: str) -> dict[str, str]:
    return {"speaker": speaker, "text": text}


def _logs(
    meeting_start: datetime,
    pattern: str,
    fail_at: LogStage | None = None,
) -> list[dict[str, Any]]:
    """Build ordered processing logs. pattern: full | partial | failed."""
    t0 = meeting_start + timedelta(minutes=5)
    stages = [
        (LogStage.INGESTION, LogStatus.SUCCESS, "Recording ingested from Zoom cloud", 420),
        (LogStage.TRANSCRIPT_PROCESSING, LogStatus.SUCCESS, "Diarization and ASR completed", 185_000),
        (LogStage.EXTRACTION, LogStatus.SUCCESS, "LLM extraction pass finished", 92_000),
        (LogStage.ASSIGNMENT, LogStatus.SUCCESS, "Owner hints resolved against directory", 12_400),
        (LogStage.NOTIFICATION, LogStatus.SUCCESS, "Review queue notifications enqueued", 3_200),
    ]
    if pattern == "partial":
        stages = stages[:2]
        out = []
        acc = 0
        for i, (st, ok, msg, ms) in enumerate(stages):
            acc += 30 * (i + 1)
            out.append(
                {
                    "stage": st.value,
                    "status": ok.value,
                    "message": msg,
                    "processing_time_ms": ms,
                    "timestamp": t0 + timedelta(seconds=acc),
                }
            )
        out.append(
            {
                "stage": LogStage.EXTRACTION.value,
                "status": LogStatus.PENDING.value,
                "message": "Queued behind higher priority jobs",
                "processing_time_ms": None,
                "timestamp": t0 + timedelta(seconds=acc + 60),
            }
        )
        return out
    if pattern == "failed" and fail_at:
        out = []
        acc = 0
        for st, ok, msg, ms in stages:
            acc += 45
            if st == fail_at:
                out.append(
                    {
                        "stage": st.value,
                        "status": LogStatus.FAILED.value,
                        "message": "Stage aborted: upstream timeout contacting model endpoint",
                        "processing_time_ms": ms,
                        "timestamp": t0 + timedelta(seconds=acc),
                    }
                )
                break
            out.append(
                {
                    "stage": st.value,
                    "status": ok.value,
                    "message": msg,
                    "processing_time_ms": ms,
                    "timestamp": t0 + timedelta(seconds=acc),
                }
            )
        return out
    out = []
    acc = 0
    for st, ok, msg, ms in stages:
        acc += 40
        out.append(
            {
                "stage": st.value,
                "status": ok.value,
                "message": msg,
                "processing_time_ms": ms,
                "timestamp": t0 + timedelta(seconds=acc),
            }
        )
    return out


def meeting_specs() -> list[dict[str, Any]]:
    """Twenty demo meetings with relational consistency."""
    specs: list[dict[str, Any]] = []

    def add(**kw: Any) -> None:
        specs.append(kw)

    # 1 — success, multiple action items
    st = _utc(days_ago=1, hour=16, minute=0)
    txt = (
        "Alex opened the Weekly Engineering Sync noting we are one week from the rollout freeze. "
        "Jordan owns the canary metrics dashboard update and committed to ship it by Thursday EOD. "
        "Sam will pair with Morgan on the checkout latency regression — please post findings in #eng-incidents by Wednesday noon. "
        "Taylor reminded everyone the design doc for partial refunds must be reviewed before Friday; Riley volunteered to drive comments. "
        "We blocked on vendor SSO cert renewal; Drew will escalate with IT and report back Monday."
    )
    add(
        title="Weekly Engineering Sync",
        start=st,
        duration_minutes=50,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["alex", "jordan", "sam", "taylor", "morgan", "riley"],
        transcript_raw=txt,
        segments=[
            _seg("Alex Chen", txt[:120]),
            _seg("Jordan Lee", "I'll have the canary dashboard ready by Thursday end of day."),
            _seg("Sam Rivera", "Morgan and I will triage checkout latency and update the channel by Wednesday noon."),
        ],
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Ship updated canary metrics dashboard for rollout freeze",
                "owner_name": "Jordan Lee",
                "due_date": "2026-04-03",
                "priority": Priority.HIGH,
                "confidence": 0.91,
                "status": ActionItemStatus.APPROVED,
                "source_snippet": "Jordan owns the canary metrics dashboard update and committed to ship it by Thursday EOD.",
            },
            {
                "description": "Post checkout latency triage findings to #eng-incidents",
                "owner_name": "Sam Rivera",
                "due_date": "2026-04-02",
                "priority": Priority.CRITICAL,
                "confidence": 0.88,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Sam will pair with Morgan on the checkout latency regression — please post findings in #eng-incidents by Wednesday noon.",
            },
            {
                "description": "Collect review comments on partial refunds design doc",
                "owner_name": "Riley Brooks",
                "due_date": "2026-04-04",
                "priority": Priority.MEDIUM,
                "confidence": 0.84,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Taylor reminded everyone the design doc for partial refunds must be reviewed before Friday; Riley volunteered to drive comments.",
            },
        ],
    )

    # 2 — product planning
    st = _utc(days_ago=2, hour=14, minute=30)
    txt = (
        "Product Planning Review focused on Q2 themes. Casey proposed prioritizing onboarding friction over net-new integrations. "
        "Jamie will circulate a one-pager on activation milestones by Tuesday. "
        "Avery flagged legal review for the new data retention copy — target completion April 8. "
        "Blake to schedule a follow-up with Sales after the pilot feedback lands next week."
    )
    add(
        title="Product Planning Review",
        start=st,
        duration_minutes=60,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["casey", "jamie", "avery", "blake", "quinn", "alex"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Share one-pager on activation milestones",
                "owner_name": "Jamie Singh",
                "due_date": "2026-04-01",
                "priority": Priority.HIGH,
                "confidence": 0.9,
                "status": ActionItemStatus.TICKET_CREATED,
                "source_snippet": "Jamie will circulate a one-pager on onboarding activation milestones by Tuesday.",
            },
            {
                "description": "Complete legal review for data retention copy",
                "owner_name": "Avery Novak",
                "due_date": "2026-04-08",
                "priority": Priority.MEDIUM,
                "confidence": 0.72,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Avery flagged legal review for the new data retention copy — target completion April 8.",
            },
        ],
    )

    # 3 — sprint retro, no action items (processed)
    st = _utc(days_ago=3, hour=17, minute=0)
    txt = (
        "Sprint Retrospective: team agreed carry-over was healthy. We celebrated faster CI times. "
        "Minor note: standups ran long twice; we'll keep an eye on it but no formal tasks recorded. "
        "Everyone felt unblockers from design were much quicker this sprint."
    )
    add(
        title="Sprint Retrospective",
        start=st,
        duration_minutes=45,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["drew", "riley", "sam", "taylor"],
        transcript_raw=txt,
        segments=[_seg("Riley Brooks", txt)],
        log_pattern="full",
        fail_at=None,
        items=[],
    )

    # 4 — client onboarding
    st = _utc(days_ago=4, hour=18, minute=0)
    txt = (
        "Client Onboarding Discussion with Acme stakeholders. Morgan walked through sandbox access. "
        "Jordan committed to send SSO configuration worksheet by tomorrow 10am PT. "
        "Client asked for a rollout plan — Alex will draft milestones covering shadow, canary, and full cutover by April 12. "
        "Open bug on CSV import edge case; Sam files Jira and links here once created."
    )
    add(
        title="Client Onboarding Discussion",
        start=st,
        duration_minutes=55,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["morgan", "jordan", "alex", "sam", "casey"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Send SSO configuration worksheet to client",
                "owner_name": "Jordan Lee",
                "due_date": "2026-03-31",
                "priority": Priority.HIGH,
                "confidence": 0.93,
                "status": ActionItemStatus.APPROVED,
                "source_snippet": "Jordan committed to send SSO configuration worksheet by tomorrow 10am PT.",
            },
            {
                "description": "Draft rollout plan: shadow, canary, full cutover",
                "owner_name": "Alex Chen",
                "due_date": "2026-04-12",
                "priority": Priority.HIGH,
                "confidence": 0.86,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Alex will draft milestones covering shadow, canary, and full cutover by April 12.",
            },
            {
                "description": "File Jira for CSV import edge case and share link",
                "owner_name": "Sam Rivera",
                "due_date": "2026-04-01",
                "priority": Priority.MEDIUM,
                "confidence": 0.79,
                "status": ActionItemStatus.REJECTED,
                "source_snippet": "Open bug on CSV import edge case; Sam files Jira and links here once created.",
            },
        ],
    )

    # 5 — bug triage
    st = _utc(days_ago=5, hour=11, minute=0)
    txt = (
        "Bug Triage Meeting: P1 on webhook retries flooding downstream — Taylor taking point, fix targeted tonight. "
        "P2 UI glitch on Safari only; Blake to bisect and update the thread by Friday. "
        "P3 documentation typo, batch into weekly docs PR. "
        "Blocker: staging replica lag masking race; Drew coordinating with infra."
    )
    add(
        title="Bug Triage Meeting",
        start=st,
        duration_minutes=40,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["taylor", "blake", "drew", "jamie", "alex"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Land fix for webhook retry storm (P1)",
                "owner_name": "Taylor Kim",
                "due_date": "2026-03-30",
                "priority": Priority.CRITICAL,
                "confidence": 0.95,
                "status": ActionItemStatus.TICKET_CREATED,
                "source_snippet": "P1 on webhook retries flooding downstream — Taylor taking point, fix targeted tonight.",
            },
            {
                "description": "Bisect Safari-only UI glitch and update thread",
                "owner_name": "Blake Ortiz",
                "due_date": "2026-04-04",
                "priority": Priority.MEDIUM,
                "confidence": 0.81,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "P2 UI glitch on Safari only; Blake to bisect and update the thread by Friday.",
            },
        ],
    )

    # 6 — release readiness
    st = _utc(days_ago=6, hour=9, minute=30)
    txt = (
        "Release Readiness Review for 2.14. Go/no-go hinges on load test green. "
        "Riley to rerun soak with the new autoscaling policy tonight. "
        "Marketing needs final release notes by Wednesday — Casey coordinating. "
        "Rollback playbook updated; Morgan verified feature flags default safe."
    )
    add(
        title="Release Readiness Review",
        start=st,
        duration_minutes=70,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["riley", "casey", "morgan", "jordan", "sam", "avery"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Rerun soak load test with new autoscaling policy",
                "owner_name": "Riley Brooks",
                "due_date": "2026-03-30",
                "priority": Priority.CRITICAL,
                "confidence": 0.89,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Riley to rerun soak with the new autoscaling policy tonight.",
            },
            {
                "description": "Finalize release notes for marketing",
                "owner_name": "Casey Wu",
                "due_date": "2026-04-02",
                "priority": Priority.MEDIUM,
                "confidence": 0.77,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Marketing needs final release notes by Wednesday — Casey coordinating.",
            },
        ],
    )

    # 7 — failed at transcript_processing
    st = _utc(days_ago=7, hour=13, minute=0)
    txt = (
        "Design Critique: Checkout Flow — participants discussed progressive disclosure and error states. "
        "Follow-ups mentioned but recording corrupted before full export."
    )
    add(
        title="Design Critique: Checkout Flow",
        start=st,
        duration_minutes=35,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.FAILED,
        people=["avery", "taylor", "quinn", "jamie"],
        transcript_raw=txt,
        segments=None,
        log_pattern="failed",
        fail_at=LogStage.TRANSCRIPT_PROCESSING,
        items=[
            {
                "description": "??? (low confidence extraction)",
                "owner_name": None,
                "due_date": None,
                "priority": Priority.LOW,
                "confidence": 0.31,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Follow-ups mentioned but recording corrupted before full export.",
            },
        ],
    )

    # 8 — failed at extraction
    st = _utc(days_ago=8, hour=10, minute=0)
    txt = (
        "Infrastructure Office Hours: we covered Kafka retention tweaks, Redis memory policy, and upcoming K8s upgrade. "
        "Drew owns the runbook refresh. Sam will open a change ticket for the cluster upgrade window April 6 overnight."
    )
    add(
        title="Infrastructure Office Hours",
        start=st,
        duration_minutes=50,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.FAILED,
        people=["drew", "sam", "blake", "morgan"],
        transcript_raw=txt,
        segments=None,
        log_pattern="failed",
        fail_at=LogStage.EXTRACTION,
        items=[],
    )

    # 9 — pending, partial pipeline
    st = _utc(days_ago=0, hour=12, minute=0)
    txt = (
        "QBR — Acme Corp: strong adoption in enterprise seats. Action: send revised success metrics deck; "
        "schedule executive workshop; confirm support SLAs by April 10."
    )
    add(
        title="QBR — Acme Corp",
        start=st,
        duration_minutes=90,
        status=MeetingStatus.PENDING,
        processing_status=ProcessingStatus.IN_PROGRESS,
        people=["alex", "casey", "morgan", "quinn"],
        transcript_raw=txt,
        segments=None,
        log_pattern="partial",
        fail_at=None,
        items=[],
    )

    # 10 — not started
    st = _utc(days_ago=0, hour=19, minute=0)
    txt = (
        "Security Review: Auth Hardening session scheduled; transcript placeholder until recording processes."
    )
    add(
        title="Security Review: Auth Hardening",
        start=st,
        duration_minutes=60,
        status=MeetingStatus.PENDING,
        processing_status=ProcessingStatus.NOT_STARTED,
        people=["jamie", "avery", "drew", "riley", "taylor"],
        transcript_raw=txt,
        segments=None,
        log_pattern="partial",
        fail_at=None,
        items=[],
        logs_override=[
            {
                "stage": LogStage.INGESTION.value,
                "status": LogStatus.PENDING.value,
                "message": "Awaiting cloud recording finalize from Zoom",
                "processing_time_ms": None,
                "timestamp": st + timedelta(minutes=2),
            }
        ],
    )

    # 11 — data pipeline success
    st = _utc(days_ago=9, hour=15, minute=0)
    txt = (
        "Data Pipeline Sync: dbt models failing on late-arriving events. "
        "Jordan to add incremental watermark guard by Tuesday. "
        "Quinn documents the new SLA dashboard in Confluence by Friday. "
        "Blocker cleared on warehouse permissions — thanks Morgan."
    )
    add(
        title="Data Pipeline Sync",
        start=st,
        duration_minutes=42,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["jordan", "quinn", "morgan", "sam", "casey"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Add incremental watermark guard for late events",
                "owner_name": "Jordan Lee",
                "due_date": "2026-04-01",
                "priority": Priority.HIGH,
                "confidence": 0.9,
                "status": ActionItemStatus.APPROVED,
                "source_snippet": "Jordan to add incremental watermark guard by Tuesday.",
            },
            {
                "description": "Document SLA dashboard in Confluence",
                "owner_name": "Quinn Foster",
                "due_date": "2026-04-04",
                "priority": Priority.LOW,
                "confidence": 0.55,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Quinn documents the new SLA dashboard in Confluence by Friday.",
            },
        ],
    )

    # 12 — hiring debrief, low confidence items
    st = _utc(days_ago=10, hour=16, minute=30)
    txt = (
        "Hiring Panel Debrief: strong systems candidate. Someone maybe follow up on references? "
        "Also discuss leveling — not sure who owns that. Compensation band refresh was mentioned loosely."
    )
    add(
        title="Hiring Panel Debrief",
        start=st,
        duration_minutes=30,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["blake", "avery", "riley", "alex"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Follow up on candidate references",
                "owner_name": None,
                "due_date": "2026-04-05",
                "priority": Priority.MEDIUM,
                "confidence": 0.42,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Someone maybe follow up on references?",
            },
            {
                "description": "Clarify leveling decision owner",
                "owner_name": None,
                "due_date": None,
                "priority": Priority.LOW,
                "confidence": 0.38,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Also discuss leveling — not sure who owns that.",
            },
        ],
    )

    # 13 — support escalation
    st = _utc(days_ago=11, hour=14, minute=0)
    txt = (
        "Customer Support Escalation: enterprise ticket on bulk export timeouts. "
        "Taylor to profile the hot path and share flame graphs by Thursday. "
        "Jamie communicates workaround steps to CS lead today."
    )
    add(
        title="Customer Support Escalation",
        start=st,
        duration_minutes=25,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["taylor", "jamie", "casey", "sam"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Profile bulk export hot path; share flame graphs",
                "owner_name": "Taylor Kim",
                "due_date": "2026-04-03",
                "priority": Priority.HIGH,
                "confidence": 0.92,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Taylor to profile the hot path and share flame graphs by Thursday.",
            },
        ],
    )

    # 14 — mobile beta
    st = _utc(days_ago=12, hour=11, minute=30)
    txt = (
        "Mobile Beta Feedback Session: crash on low-memory devices, push notification duplicates, "
        "and positive comments on offline mode. Morgan files tickets; Sam coordinates next beta build April 5."
    )
    add(
        title="Mobile Beta Feedback Session",
        start=st,
        duration_minutes=48,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["morgan", "sam", "blake", "drew"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "File tickets for low-memory crash and duplicate pushes",
                "owner_name": "Morgan Patel",
                "due_date": "2026-04-01",
                "priority": Priority.HIGH,
                "confidence": 0.87,
                "status": ActionItemStatus.APPROVED,
                "source_snippet": "Morgan files tickets; crash on low-memory devices, push notification duplicates.",
            },
            {
                "description": "Coordinate next mobile beta build",
                "owner_name": "Sam Rivera",
                "due_date": "2026-04-05",
                "priority": Priority.MEDIUM,
                "confidence": 0.83,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Sam coordinates next beta build April 5.",
            },
        ],
    )

    # 15 — API deprecation
    st = _utc(days_ago=13, hour=9, minute=0)
    txt = (
        "API Deprecation Workshop: v1 sunset July 1. Riley publishes migration guide; "
        "Jordan adds linter warnings in SDK; customer comms draft due April 15."
    )
    add(
        title="API Deprecation Workshop",
        start=st,
        duration_minutes=55,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["riley", "jordan", "alex", "avery", "taylor"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Publish v1 to v2 migration guide",
                "owner_name": "Riley Brooks",
                "due_date": "2026-04-07",
                "priority": Priority.HIGH,
                "confidence": 0.9,
                "status": ActionItemStatus.TICKET_CREATED,
                "source_snippet": "Riley publishes migration guide.",
            },
            {
                "description": "Add SDK linter warnings for deprecated v1 calls",
                "owner_name": "Jordan Lee",
                "due_date": "2026-04-10",
                "priority": Priority.MEDIUM,
                "confidence": 0.85,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Jordan adds linter warnings in SDK.",
            },
            {
                "description": "Draft customer communication for API sunset",
                "owner_name": "Alex Chen",
                "due_date": "2026-04-15",
                "priority": Priority.MEDIUM,
                "confidence": 0.8,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "customer comms draft due April 15.",
            },
        ],
    )

    # 16 — incident postmortem
    st = _utc(days_ago=14, hour=17, minute=30)
    txt = (
        "Incident Postmortem: cache stampede during flash sale. "
        "Action items: tighten circuit breaker defaults (Drew), add playbook section on traffic shaping (Jamie), "
        "schedule game day April 20 (Casey)."
    )
    add(
        title="Incident Postmortem",
        start=st,
        duration_minutes=65,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["drew", "jamie", "casey", "sam", "morgan", "taylor"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Tighten circuit breaker defaults after stampede",
                "owner_name": "Drew Martinez",
                "due_date": "2026-04-02",
                "priority": Priority.CRITICAL,
                "confidence": 0.94,
                "status": ActionItemStatus.APPROVED,
                "source_snippet": "tighten circuit breaker defaults (Drew)",
            },
            {
                "description": "Add traffic shaping section to incident playbook",
                "owner_name": "Jamie Singh",
                "due_date": "2026-04-05",
                "priority": Priority.HIGH,
                "confidence": 0.88,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "add playbook section on traffic shaping (Jamie)",
            },
            {
                "description": "Schedule resilience game day",
                "owner_name": "Casey Wu",
                "due_date": "2026-04-20",
                "priority": Priority.MEDIUM,
                "confidence": 0.82,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "schedule game day April 20 (Casey).",
            },
        ],
    )

    # 17 — dependencies forum
    st = _utc(days_ago=15, hour=13, minute=30)
    txt = (
        "Cross-team Dependencies Forum: payments team waiting on fraud rules API. "
        "Blake to unblock schema review tomorrow. No other formal tasks."
    )
    add(
        title="Cross-team Dependencies Forum",
        start=st,
        duration_minutes=30,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["blake", "sam", "jordan", "riley"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Unblock fraud rules API schema review",
                "owner_name": "Blake Ortiz",
                "due_date": "2026-03-31",
                "priority": Priority.HIGH,
                "confidence": 0.91,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Blake to unblock schema review tomorrow.",
            },
        ],
    )

    # 18 — UX research readout
    st = _utc(days_ago=16, hour=10, minute=30)
    txt = (
        "UX Research Readout on search discoverability. Key insight: users miss filters. "
        "Taylor prototypes quick wins; Avery aligns with design system tokens next sprint."
    )
    add(
        title="UX Research Readout",
        start=st,
        duration_minutes=44,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["taylor", "avery", "quinn", "morgan"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Prototype search filter quick wins",
                "owner_name": "Taylor Kim",
                "due_date": "2026-04-06",
                "priority": Priority.MEDIUM,
                "confidence": 0.86,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Taylor prototypes quick wins",
            },
        ],
    )

    # 19 — compliance dry run
    st = _utc(days_ago=17, hour=12, minute=0)
    txt = (
        "Compliance Training Dry Run: timeline for SOC2 evidence collection discussed. "
        "No explicit owners named; team will follow up offline."
    )
    add(
        title="Compliance Training Dry Run",
        start=st,
        duration_minutes=40,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["avery", "jamie", "drew"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[],
    )

    # 20 — vendor evaluation
    st = _utc(days_ago=18, hour=15, minute=45)
    txt = (
        "Vendor Evaluation — Transcription Tooling: compared accuracy, latency, and on-prem option. "
        "Decision: pilot secondary vendor for EMEA meetings. Riley schedules pilot kickoff April 9. "
        "Morgan tracks cost projections for finance."
    )
    add(
        title="Vendor Evaluation — Transcription Tooling",
        start=st,
        duration_minutes=50,
        status=MeetingStatus.COMPLETED,
        processing_status=ProcessingStatus.PROCESSED,
        people=["riley", "morgan", "alex", "casey", "blake"],
        transcript_raw=txt,
        segments=None,
        log_pattern="full",
        fail_at=None,
        items=[
            {
                "description": "Schedule EMEA transcription pilot kickoff",
                "owner_name": "Riley Brooks",
                "due_date": "2026-04-09",
                "priority": Priority.MEDIUM,
                "confidence": 0.84,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Riley schedules pilot kickoff April 9.",
            },
            {
                "description": "Send transcription cost projections to finance",
                "owner_name": "Morgan Patel",
                "due_date": "2026-04-08",
                "priority": Priority.LOW,
                "confidence": 0.68,
                "status": ActionItemStatus.PENDING_REVIEW,
                "source_snippet": "Morgan tracks cost projections for finance.",
            },
        ],
    )

    return specs


async def _seed_projects_catalog(
    db: Any, specs: list[dict[str, Any]], now: datetime
) -> dict[str, ObjectId]:
    """Insert `projects` docs (canonical initiative + long-form context). Meetings reference by project_id."""
    rows: dict[str, dict[str, str | None]] = {}
    for v in CONTEXT_PRESET.values():
        n = v["project_theme"]
        rows[n] = {
            "context_developer": v.get("context_developer"),
            "context_pm": v.get("context_pm"),
        }
    from app.seed.volume_seed import PRODUCTS, STREAMS, _long_dev_context, _long_pm_context

    for product in PRODUCTS:
        for stream in STREAMS:
            n = f"{product} program · {stream}"
            rows[n] = {
                "context_developer": _long_dev_context(product, stream),
                "context_pm": _long_pm_context(product, stream),
            }
    for spec in specs:
        if spec["title"] not in CONTEXT_PRESET:
            t = spec["title"]
            rows[t] = {
                "context_developer": (
                    "Add engineering / IC next steps from the meeting detail page — no preset for this title."
                ),
                "context_pm": (
                    "Add PM / stakeholder next steps from the meeting detail page — no preset for this title."
                ),
            }
    name_to_id: dict[str, ObjectId] = {}
    from app.services.related_links import related_links_for_project_name

    for name in sorted(rows.keys(), key=str.casefold):
        pl = rows[name]
        res = await db.projects.insert_one(
            {
                "name": name,
                "context_developer": pl.get("context_developer"),
                "context_pm": pl.get("context_pm"),
                "related_links": related_links_for_project_name(name),
                "created_at": now,
                "updated_at": now,
            }
        )
        name_to_id[name] = res.inserted_id
    return name_to_id


async def seed_database() -> None:
    db = get_db()
    for name in (
        "meeting_participants",
        "action_items",
        "processing_logs",
        "transcripts",
        "meetings",
        "projects",
        "participants",
    ):
        await db[name].delete_many({})

    slug_to_pid: dict[str, ObjectId] = {}
    for slug, (display_name, email) in POOL.items():
        doc: dict[str, Any] = {
            "display_name": display_name,
            "created_at": datetime.now(timezone.utc),
        }
        if email is not None:
            doc["email"] = email
        res = await db.participants.insert_one(doc)
        slug_to_pid[slug] = res.inserted_id

    now = datetime.now(timezone.utc)
    specs = meeting_specs()
    theme_to_pid = await _seed_projects_catalog(db, specs, now)

    project_name_to_slugs: dict[str, set[str]] = {}
    for spec in specs:
        if spec["title"] in CONTEXT_PRESET:
            pname = CONTEXT_PRESET[spec["title"]]["project_theme"]
        else:
            pname = spec["title"]
        project_name_to_slugs.setdefault(pname, set()).update(spec["people"])

    for pname, poid in theme_to_pid.items():
        slugs = project_name_to_slugs.get(pname, set())
        member_ids = list({slug_to_pid[s] for s in slugs if s in slug_to_pid})
        await db.projects.update_one({"_id": poid}, {"$set": {"team_member_ids": member_ids}})

    for spec in specs:
        people: list[str] = spec["people"]
        pc = len(people)
        meeting_doc: dict[str, Any] = {
            "title": spec["title"],
            "source": "zoom",
            "start_time": spec["start"],
            "duration_minutes": spec["duration_minutes"],
            "status": spec["status"].value,
            "processing_status": spec["processing_status"].value,
            "participants_count": pc,
            "created_at": now,
            "updated_at": now,
        }
        if spec["title"] in CONTEXT_PRESET:
            pname = CONTEXT_PRESET[spec["title"]]["project_theme"]
        else:
            pname = spec["title"]
        meeting_doc["project_id"] = theme_to_pid[pname]
        meeting_doc["project_theme"] = pname
        mres = await db.meetings.insert_one(meeting_doc)
        mid = mres.inserted_id

        for slug in people:
            await db.meeting_participants.insert_one(
                {
                    "meeting_id": mid,
                    "participant_id": slug_to_pid[slug],
                    "role": "attendee",
                    "joined_at": spec["start"],
                }
            )

        raw = spec["transcript_raw"]
        tlen = len(raw)
        await db.transcripts.insert_one(
            {
                "meeting_id": mid,
                "raw_text": raw,
                "segments": spec.get("segments"),
                "transcript_length": tlen,
                "created_at": spec["start"] + timedelta(minutes=spec["duration_minutes"]),
            }
        )

        for it in spec["items"]:
            await db.action_items.insert_one(
                {
                    "meeting_id": mid,
                    "description": it["description"],
                    "owner_name": it.get("owner_name"),
                    "due_date": it.get("due_date"),
                    "priority": it["priority"].value,
                    "confidence": it["confidence"],
                    "status": it["status"].value,
                    "source_snippet": it.get("source_snippet"),
                    "created_at": now,
                    "updated_at": now,
                }
            )

        if "logs_override" in spec:
            log_entries = spec["logs_override"]
        else:
            log_entries = _logs(spec["start"], spec["log_pattern"], spec.get("fail_at"))
        for le in log_entries:
            await db.processing_logs.insert_one(
                {
                    "meeting_id": mid,
                    "stage": le["stage"],
                    "status": le["status"],
                    "message": le["message"],
                    "processing_time_ms": le.get("processing_time_ms"),
                    "timestamp": le["timestamp"],
                }
            )

    from app.seed.volume_seed import insert_high_volume_meetings

    name_by_slug = {slug: POOL[slug][0] for slug in POOL}
    await insert_high_volume_meetings(
        db,
        slug_to_pid,
        now,
        count=48,
        name_by_slug=name_by_slug,
        theme_to_pid=theme_to_pid,
    )

    await db.meetings.create_index("start_time")
    await db.transcripts.create_index("meeting_id", unique=True)
    await db.action_items.create_index("meeting_id")
    await db.processing_logs.create_index("meeting_id")
    await db.meeting_participants.create_index([("meeting_id", 1), ("participant_id", 1)], unique=True)
