"""
High-volume synthetic meetings for demos: long transcripts/contexts and explicit participant roles.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from app.domain.enums import (
    ActionItemStatus,
    LogStage,
    LogStatus,
    MeetingStatus,
    Priority,
    ProcessingStatus,
)

ROLE_SEQUENCE = [
    "engineering_lead",
    "developer",
    "developer",
    "product_manager",
    "designer",
    "program_manager",
    "stakeholder",
    "qa_lead",
]

STREAMS = [
    "Identity & access",
    "Billing & monetization",
    "Data platform",
    "Mobile experience",
    "Search & discovery",
    "Observability",
    "Security & compliance",
    "Customer success tooling",
]

PRODUCTS = ["Northstar", "Aurora", "Atlas", "Vertex", "Pulse", "Meridian", "Quartz", "Helix"]

MEETING_KINDS = [
    "Program checkpoint",
    "Technical design review",
    "Cross-functional sync",
    "Risk review",
    "Milestone demo",
    "Dependency negotiation",
    "Readiness gate",
    "Quarterly deep-dive",
]


def _paragraphs(project: str, stream: str, kind: str) -> list[str]:
    return [
        f"Chair opened the {kind.lower()} for the {stream} track under the {project} program. "
        f"The group aligned on the current definition of done for the integration milestones and "
        f"confirmed that architecture sign-off from the platform council is still the gating item for "
        f"production traffic in the pilot region.",
        f"Engineering highlighted that the {stream} service mesh rollout exposed uneven timeout behavior "
        f"between regional clusters; action is to reproduce under load in the shared perf environment and "
        f"publish a short write-up with flame graphs before the next office hours. Product asked for a "
        f"customer-safe summary of impact windows for the top three enterprise tenants.",
        f"Discussion turned to contract testing between the billing orchestration layer and the new "
        f"usage aggregation pipeline. Several edge cases around partial month true-ups and credit notes "
        f"were enumerated; the team agreed to extend the golden fixture set and to add a regression suite "
        f"that runs on every merge to main for the affected services.",
        f"Program management raised staffing concerns for the parallel hardening sprint: two senior "
        f"engineers are double-booked on incident response rotation. A proposal to borrow capacity from "
        f"the adjacent data ingestion squad for two weeks was accepted pending director approval; PM to "
        f"follow up with functional leads by Wednesday.",
        f"Design reviewed the updated flows for administrator approval of high-risk configuration changes. "
        f"Open questions include audit log retention parity across regions and whether the mobile admin "
        f"app should defer to the web experience for bulk approvals. UX research readout is scheduled; "
        f"engineering to spike feasibility of offline-safe draft mode.",
        f"Security and compliance joined for thirty minutes to walk through the control mapping worksheet "
        f"for SOC2 evidence collection. No new findings; two items remain in the exceptions log with "
        f"target remediation dates in the next quarter. Action: attach meeting notes and recording links "
        f"to the compliance workspace folder for the external auditor packet.",
        f"Closing: next checkpoint in ten business days; owners to update the shared RAID log with new "
        f"risks from this session. Standby support for the upcoming regional holiday was confirmed; "
        f"on-call rotation adjusted in PagerDuty. Everyone encouraged to flag scope creep early given "
        f"the fixed launch window for {project}.",
    ]


def _long_dev_context(project: str, stream: str) -> str:
    parts = [
        f"[Engineering] {project} / {stream}: prioritize stabilizing the cross-region replication lag "
        f"that showed up after last week's config push. Pair on bisect; post repro steps "
        f"and query plans in the runbook.",
        "Ship incremental backfill job behind a feature flag; default off in prod until soak completes. "
        "Add dashboards for lag p95/p99 and alert if sustained above SLO for 15 minutes.",
        "Refactor the shared retry helper to use jittered exponential backoff; align with platform "
        "standard library version 2.4. Document breaking changes in the internal changelog.",
        "Tech debt backlog: migrate three remaining cron jobs to the workflow engine; estimate 5–8 "
        "points each. Block dependency: secrets rotation coordinated with security on April 2 window.",
        "Performance: run A/B on payload compression for bulk export path; validate CPU tradeoff on "
        "smallest instance class. Share results in #perf-core with graphs.",
        "Developer experience: improve local stack bootstrap time; target under 90 seconds cold start. "
        "Spike using pre-built images from the dev registry.",
        "On-call: page threshold for 5xx rate on checkout edge raised temporarily during soak; revert "
        "after green light from SRE. Post-incident template updated for partial degradation scenarios.",
        "Data quality: reconcile warehouse late-arriving facts with streaming summaries; document "
        "watermark strategy for downstream consumers.",
    ]
    return "\n\n".join(parts)


def _long_pm_context(project: str, stream: str) -> str:
    parts = [
        f"[Product / PM] {project}: align GTM narrative with the phased rollout—week 1 shadow, "
        f"week 2 canary at 5% traffic, week 3 full region contingent on error budget.",
        f"Stakeholder map: enterprise champions, mid-market CS pod, and two design "
        f"partners for {stream}. Schedule executive readout after milestone demo; deck due EOW.",
        "Success metrics: activation rate, time-to-first-value, support ticket volume by category, "
        "and NPS pulse for pilot cohort. PM to wire read-only views into the quarterly business review pack.",
        "Risks: competitor announcement rumored same week; prepare FAQ and battlecard. Legal review "
        "for updated terms snippet tied to new usage limits—target completion April 6.",
        "Customer comms: draft in-app banner + email for maintenance window; localization for DE/FR "
        "if time permits else English-only with follow-up.",
        "Sales enablement: one-pager on differentiation vs legacy bundle; include three customer quotes "
        "from beta. Training office hours April 11.",
        "Program: RAID log hygiene—close items older than 60 days or re-baseline. Dependencies on "
        "vendor pen-test slot confirmed for May.",
    ]
    return "\n\n".join(parts)


def _action_templates(project: str) -> list[dict[str, Any]]:
    return [
        {
            "description": f"Publish {project} rollout checklist and owner matrix in Confluence",
            "owner_name": None,
            "due_date": None,
            "priority": Priority.HIGH,
            "confidence": 0.82,
            "status": ActionItemStatus.PENDING_REVIEW,
            "source_snippet": f"fixed launch window for {project}",
        },
        {
            "description": "Schedule director sign-off on cross-squad borrow proposal",
            "owner_name": "Casey Wu",
            "due_date": "2026-04-05",
            "priority": Priority.MEDIUM,
            "confidence": 0.76,
            "status": ActionItemStatus.PENDING_REVIEW,
            "source_snippet": "borrow capacity from the adjacent data ingestion squad",
        },
        {
            "description": "Extend golden fixture set for billing edge cases",
            "owner_name": "Jordan Lee",
            "due_date": "2026-04-08",
            "priority": Priority.HIGH,
            "confidence": 0.88,
            "status": ActionItemStatus.APPROVED,
            "source_snippet": "extend the golden fixture set",
        },
    ]


def _logs_volume(meeting_start: datetime) -> list[dict[str, Any]]:
    t0 = meeting_start + timedelta(minutes=3)
    stages = [
        (LogStage.INGESTION, LogStatus.SUCCESS, "Recording ingested from Zoom cloud", 380),
        (LogStage.TRANSCRIPT_PROCESSING, LogStatus.SUCCESS, "ASR + diarization completed", 142_000),
        (LogStage.EXTRACTION, LogStatus.SUCCESS, "Structured extraction pass completed", 88_000),
        (LogStage.ASSIGNMENT, LogStatus.SUCCESS, "Role hints matched to directory", 11_200),
        (LogStage.NOTIFICATION, LogStatus.SUCCESS, "Review notifications enqueued", 2_900),
    ]
    out = []
    acc = 0
    for st, ok, msg, ms in stages:
        acc += 35
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


async def insert_high_volume_meetings(
    db: Any,
    slug_to_pid: dict[str, ObjectId],
    now: datetime,
    *,
    count: int = 48,
    seed: int = 42,
    name_by_slug: dict[str, str] | None = None,
    theme_to_pid: dict[str, ObjectId] | None = None,
) -> None:
    """Insert many large meetings with role-tagged participants and rich context."""
    from app.seed.demo_data import _logs as demo_logs

    rng = random.Random(seed)
    pool_slugs = list(slug_to_pid.keys())
    names = name_by_slug or {}
    themes = theme_to_pid or {}

    for i in range(count):
        stream = STREAMS[i % len(STREAMS)]
        product = PRODUCTS[(i * 3) % len(PRODUCTS)]
        kind = MEETING_KINDS[i % len(MEETING_KINDS)]
        title = f"{stream} — {product} ({kind} #{i + 1:02d})"

        days_ago = min(45, (i * 2) % 46)
        hour = 9 + (i % 8)
        minute = 10 * (i % 6)
        start = datetime.now(timezone.utc).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        ) - timedelta(days=days_ago)

        n_people = rng.randint(4, 7)
        people = rng.sample(pool_slugs, k=min(n_people, len(pool_slugs)))

        status_roll = rng.random()
        if status_roll < 0.78:
            proc = ProcessingStatus.PROCESSED
            meet_st = MeetingStatus.COMPLETED
        elif status_roll < 0.88:
            proc = ProcessingStatus.IN_PROGRESS
            meet_st = MeetingStatus.PENDING
        elif status_roll < 0.93:
            proc = ProcessingStatus.NOT_STARTED
            meet_st = MeetingStatus.PENDING
        else:
            proc = ProcessingStatus.FAILED
            meet_st = MeetingStatus.COMPLETED

        paras = _paragraphs(product, stream, kind)
        raw_text = "\n\n".join(paras)
        segments = []
        for j, sl in enumerate(people[:3]):
            if j < len(paras):
                full = names.get(sl, "Participant")
                first = full.split()[0] if full else "Participant"
                segments.append(
                    {"speaker": first, "text": paras[j][: min(220, len(paras[j]))]}
                )

        pname = f"{product} program · {stream}"
        proj_id = themes.get(pname)
        meeting_doc: dict[str, Any] = {
            "title": title,
            "source": "zoom",
            "start_time": start,
            "duration_minutes": 30 + (i % 5) * 15,
            "status": meet_st.value,
            "processing_status": proc.value,
            "participants_count": len(people),
            "created_at": now,
            "updated_at": now,
            "project_theme": pname,
        }
        if proj_id is not None:
            meeting_doc["project_id"] = proj_id
        else:
            meeting_doc["context_developer"] = _long_dev_context(product, stream)
            meeting_doc["context_pm"] = _long_pm_context(product, stream)

        mres = await db.meetings.insert_one(meeting_doc)
        mid = mres.inserted_id

        for idx, slug in enumerate(people):
            role = ROLE_SEQUENCE[idx % len(ROLE_SEQUENCE)]
            await db.meeting_participants.insert_one(
                {
                    "meeting_id": mid,
                    "participant_id": slug_to_pid[slug],
                    "role": role,
                    "joined_at": start,
                }
            )

        tlen = len(raw_text)
        await db.transcripts.insert_one(
            {
                "meeting_id": mid,
                "raw_text": raw_text,
                "segments": segments,
                "transcript_length": tlen,
                "created_at": start + timedelta(minutes=meeting_doc["duration_minutes"]),
            }
        )

        items = _action_templates(product)
        if proc == ProcessingStatus.FAILED:
            items = items[:1]
        elif rng.random() < 0.12:
            items = []

        for it in items:
            st = it["status"]
            if isinstance(st, ActionItemStatus):
                st = st.value
            pr = it["priority"]
            if isinstance(pr, Priority):
                pr = pr.value
            await db.action_items.insert_one(
                {
                    "meeting_id": mid,
                    "description": it["description"],
                    "owner_name": it.get("owner_name"),
                    "due_date": it.get("due_date"),
                    "priority": pr,
                    "confidence": it["confidence"],
                    "status": st,
                    "source_snippet": it.get("source_snippet"),
                    "created_at": now,
                    "updated_at": now,
                }
            )

        if proc == ProcessingStatus.PROCESSED:
            log_entries = _logs_volume(start)
        elif proc == ProcessingStatus.IN_PROGRESS:
            log_entries = _logs_volume(start)[:3]
        elif proc == ProcessingStatus.FAILED:
            log_entries = demo_logs(start, "failed", LogStage.EXTRACTION)
        else:
            log_entries = demo_logs(start, "partial")

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
