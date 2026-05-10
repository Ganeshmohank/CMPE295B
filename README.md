# CMPE 295B — Meeting Intelligence

A full-stack app for **meeting ingestion, transcripts, action-item review**, and **processing observability**. The backend is a **FastAPI** service on **MongoDB**; the UI is **React + Vite + TypeScript**.

---

## Overview

- **Dashboard** — Rolling metrics, searchable/sortable meeting list, initiative (project theme) hints for filters.
- **Meetings** — Per-meeting detail: metadata, transcript (with segments), related links, participants, action items, processing logs.
- **Action items** — Human-in-the-loop **review queue** (approve / reject / bulk per meeting), editable fields before approval.
- **Projects** — Initiative catalog, per-project context (developer / PM), and team rosters linked to meetings.

---

## Repository layout

| Path | Role |
|------|------|
| `meeting-intelligence/backend/` | FastAPI app (`app/`), MongoDB via Motor |
| `meeting-intelligence/frontend/` | React SPA (Vite) |
| `meeting-intelligence/docs/database-schema.md` | Mermaid ER diagram (same model as below) |

---

## Prerequisites

- **Python 3.11+** (recommended), **Node.js 18+**, **MongoDB** (local or Atlas)

---

## Quick start

### 1. MongoDB

Run MongoDB locally (default `mongodb://localhost:27017`) or point `MONGODB_URI` at your cluster.

### 2. Backend

```bash
cd meeting-intelligence/backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # edit if needed
uvicorn app.main:app --reload --port 8000
```

- **Health:** `GET http://127.0.0.1:8000/health`
- **Interactive API docs:** `http://127.0.0.1:8000/docs` (OpenAPI)

Optional seed data (if your repo includes a seed script):

```bash
python scripts/seed.py
```

### 3. Frontend

```bash
cd meeting-intelligence/frontend
npm install
npm run dev
```

App expects the API at the same host defaults; CORS allows `http://localhost:5173` and `http://127.0.0.1:5173`.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | Mongo connection string |
| `DATABASE_NAME` | `meeting_intelligence` | Database name |

Defined in `meeting-intelligence/backend/app/config.py` (via `.env`).

The HTTP API is mounted under **`/api`** (see below).

---

## Database schema (MongoDB)

All `_id` fields are **ObjectId** unless noted. Relationships are by reference fields, not SQL joins.

### Collections and fields

#### `projects`

| Field | Type | Notes |
|-------|------|--------|
| `_id` | ObjectId | Primary key |
| `name` | string | Initiative / theme label |
| `context_developer` | string? | Long-form IC/engineering context |
| `context_pm` | string? | Long-form PM/stakeholder context |
| `created_at`, `updated_at` | datetime | Audit |

#### `participants`

| Field | Type | Notes |
|-------|------|--------|
| `_id` | ObjectId | Primary key |
| `display_name` | string | |
| `email` | string | Unique when present (sparse index) |
| `created_at` | datetime | |

#### `meetings`

| Field | Type | Notes |
|-------|------|--------|
| `_id` | ObjectId | Primary key |
| `project_id` | ObjectId? | Optional FK → `projects` |
| `title` | string | |
| `source` | string | e.g. zoom |
| `start_time` | datetime | |
| `duration_minutes` | int | |
| `status` | string | Meeting lifecycle |
| `processing_status` | string | Pipeline state |
| `participants_count` | int | Denormalized |
| `project_theme` | string? | Denormalized display name for initiatives |
| `context_developer`, `context_pm` | string? | Optional overrides; null inherits project |
| `created_at`, `updated_at` | datetime | |
| `related_links` | array? | Optional embedded link metadata (see API responses) |

#### `meeting_participants`

| Field | Type | Notes |
|-------|------|--------|
| `_id` | ObjectId | Primary key |
| `meeting_id` | ObjectId | FK → `meetings` |
| `participant_id` | ObjectId | FK → `participants` |
| `role` | string | |
| `joined_at` | datetime | |

Unique compound index on `(meeting_id, participant_id)`.

#### `transcripts`

| Field | Type | Notes |
|-------|------|--------|
| `_id` | ObjectId | Primary key |
| `meeting_id` | ObjectId | FK → `meetings` (unique index: one transcript per meeting) |
| `raw_text` | string | |
| `segments` | array | Structured chunks (e.g. speaker/time) |
| `transcript_length` | int | |
| `created_at` | datetime | |

#### `action_items`

| Field | Type | Notes |
|-------|------|--------|
| `_id` | ObjectId | Primary key |
| `meeting_id` | ObjectId | FK → `meetings` |
| `description` | string | |
| `owner_name` | string | |
| `due_date` | string | |
| `priority` | string | |
| `confidence` | float | Model confidence |
| `status` | string | Includes review workflow states |
| `source_snippet` | string? | Evidence from transcript |
| `created_at`, `updated_at` | datetime | |

#### `processing_logs`

| Field | Type | Notes |
|-------|------|--------|
| `_id` | ObjectId | Primary key |
| `meeting_id` | ObjectId | FK → `meetings` |
| `stage` | string | Pipeline stage |
| `status` | string | Success/failure etc. |
| `message` | string | |
| `processing_time_ms` | int | |
| `timestamp` | datetime | |

### Indexes (application-managed)

Created at startup (`ensure_indexes`): `projects.name`; `meetings` on `start_time`, `project_id`, `status`, `processing_status`; `transcripts.meeting_id` (unique); `action_items` on `meeting_id`, `status`; `processing_logs` on `meeting_id` and `timestamp` (desc); `meeting_participants` unique pair; `participants.email` unique sparse.

### ER diagram

See `meeting-intelligence/docs/database-schema.md` for the same model as a **Mermaid** `erDiagram`.

---

## Approvals, Notion recap, and Atlassian errors

### What runs when you approve

Approving an action item (single **Approve**, **Approve all** on the meeting page, or `PATCH` to `approved` from `pending_review`) does two things in the API:

1. **Notion meeting recap** — A background task calls the same recap logic as `POST /api/meetings/{id}/notion-recap`. If a recap page already exists for the meeting, it is skipped unless you call that endpoint with `force: true` or use **Post again** in the UI. This runs even when `NOTION_POST_RECAP_AFTER_PROCESSING=false` (that flag only disables automatic recap right after ingest; approval still tries recap so reviewers can drive publishing).

2. **Auto-orchestration** — When `MCP_MODE=live` and Jira (and related) env vars are set, the classifier may create/update Jira issues, post Confluence comments, calendar events, etc. Failures show up in execution / activity logs (for example **Confluence error** entries).

### Confluence errors on approval (e.g. HTTP 401 + HTML)

Confluence uses the same **Atlassian Cloud** site and API token as Jira (`JIRA_URL`, `JIRA_API_MAIL`, `JIRA_API_KEY`). A **`401`** response whose body looks like an **HTML login page** almost always means authentication failed, not that “Confluence is down.”

Checklist:

- **`JIRA_URL`** is exactly your Cloud site root: `https://YOUR_SITE.atlassian.net` (no `/wiki`, no issue path).
- **`JIRA_API_MAIL`** is the primary email of the Atlassian account that owns the token.
- **`JIRA_API_KEY`** is a current [API token](https://id.atlassian.com/manage-profile/security/api-tokens) (revoke old tokens if unsure).
- The account has **Confluence** access and permission to comment on the space you search (optional **`CONFLUENCE_SPACE_KEY`** narrows CQL search).
- **`MCP_MODE=live`** so Confluence calls are not mocked.

The API surfaces a shorter error message for HTML 401 responses; full troubleshooting is here in the README.

---

## HTTP API

Base URL: **`/api`** (e.g. `http://127.0.0.1:8000/api/...`).  
IDs in path parameters are **MongoDB ObjectId strings** (24 hex chars).

### Root (outside `/api`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness: `{ "status": "ok" }` |

---

### Dashboard — `/api/dashboard`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/project-themes` | Distinct initiative labels for autocomplete. Query: `q` (optional substring, case-insensitive). |
| `GET` | `/summary` | Aggregated dashboard metrics. Query: `window_days` — **`7`** or **`30`** (rolling window). |
| `GET` | `/meetings` | Paginated meeting list for the main table. Query: `page` (≥1), `page_size` (1–10), `q` (title/source substring), `pipeline` (`meetings.processing_status` or omit / `all`), `focus_pending` (bool — only meetings with pending review items), `sort` — `date_desc` \| `date_asc` \| `title` \| `actions_desc` \| `pending_first`. |

---

### Projects — `/api/projects`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/catalog`, `/`, `` | Unified initiative catalog (`ProjectListItem[]`). Themes from `projects` plus orphan `meetings.project_theme` names (empty `id` until a project doc exists). |
| `GET` | `/{project_id}` | Single project with contexts (`ProjectOut`). |
| `GET` | `/{project_id}/team-members` | Roster members for the initiative (`MeetingParticipantOut[]`). |

---

### Meetings — `/api/meetings`

| Method | Path | Description |
|--------|------|-------------|
| `PATCH` | `/{meeting_id}/context` | Update meeting metadata: optional `project_id`, `project_theme`, context overrides, etc. (`MeetingContextPatch` body). Returns `MeetingMetadata`. |
| `POST` | `/{meeting_id}/team-members` | Add attendee + optional link to project roster (`MeetingTeamMemberCreate`: `display_name`, `email`, `add_to_linked_project`). Returns `MeetingParticipantOut`. |
| `GET` | `/{meeting_id}` | Full detail: meeting, transcript, action items, logs, participants (`MeetingDetailResponse`). |
| `GET` | `/{meeting_id}/meta` | Lightweight metadata only (`MeetingMetadata`). |
| `POST` | `/{meeting_id}/notion-recap` | Create Notion recap page (`force` optional). Also run in the background after action-item approval; see **Approvals, Notion recap, and Atlassian errors**. |

---

### Action items — `/api/action-items`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/review-queue` | Paginated pending-review items across meetings. Query: `page`, `page_size` (1–10). |
| `GET` | `/{item_id}/review-detail` | Single pending item with meeting context for the review drawer. |
| `PATCH` | `/{item_id}` | Update editable fields (`ActionItemUpdate` body). Moving `status` from `pending_review` to `approved` sets `approved_at` and schedules **Notion recap** (same as POST approve). |
| `POST` | `/{item_id}/approve` | Approve extracted item. Schedules **Notion recap** (background) and **auto-orchestration** when enabled. |
| `POST` | `/{item_id}/reject` | Reject item (optional `ActionItemRejectBody`). |
| `POST` | `/meetings/{meeting_id}/bulk-approve` | Approve all pending items for that meeting. Returns `{ "updated": number }`. Schedules **one** Notion recap task for the meeting and orchestration per item. |
| `POST` | `/meetings/{meeting_id}/bulk-reject` | Reject all pending items for that meeting. Returns `{ "updated": number }`. |

---

### Logs — `/api/logs`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/processing` | Paginated processing pipeline logs. Query: `page`, `page_size` (1–10), optional `stage`, `status` (enum filters). |

---

## OpenAPI

Run the backend and open **`/docs`** for request/response schemas, try-it-out, and enums (e.g. log stages).

---

## License / course

CMPE 295B course project — use and attribution per your program’s policy.
