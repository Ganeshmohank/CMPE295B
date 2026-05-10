# Station Alpha — Zoom ingest

Node service that receives **Zoom account webhooks**, sends a **Recall.ai** bot into meetings, then writes **transcripts** and **action items** into the same **MongoDB** collections used by Meeting Intelligence (FastAPI + React).

## Run locally

1. Copy `.env.example` → `.env` and fill secrets (same `MONGODB_URI` / `DATABASE_NAME` as `../backend`).
2. Start MongoDB, FastAPI (`../backend`), and React (`../frontend`) as usual.
3. Start this service:

```bash
cd station-alpha
npm install
npm run dev
```

Default URL: `http://127.0.0.1:3001`

## Expose HTTPS for Zoom (tunnel)

Zoom requires a **public HTTPS** URL. For development, use Cloudflare Quick Tunnel:

```bash
npx cloudflared tunnel --url http://localhost:3001
```

Copy the printed URL (e.g. `https://something.trycloudflare.com`).

### Zoom Marketplace → point these at **tunnel + Station Alpha**

| Setting | URL |
|--------|-----|
| S2S app — Event subscription | `https://<tunnel-host>/zoom/events` |
| General app — Event subscription (if enabled) | same |
| General app — OAuth redirect | `https://<tunnel-host>/zoom/oauth/callback` |
| General app — Bot endpoint | `https://<tunnel-host>/zoom/botmessage` |

Set `PUBLIC_URL=https://<tunnel-host>` in `.env` (no trailing slash) if you use OAuth.

**Note:** Quick tunnel URLs change each run — update Zoom and `.env` whenever the tunnel restarts.

## Flow

1. **`meeting.started`** — Inserts/updates a `meetings` row (`status: pending`, `processing_status: in_progress`), sends Recall bot, stores `recall_bot_id`.
2. **`meeting.ended`** — Logs “waiting for transcript”; when Recall finishes, saves `transcripts`, inserts `action_items` (`pending_review`), sets `processing_status: processed`, `status: completed`.

The React app reads data only from **FastAPI**; it does not talk to Station Alpha directly.

### Optional: Notion meeting recap

If you set `MEETING_INTELLIGENCE_API_URL` (e.g. `http://127.0.0.1:8000/api`) and configure `NOTION_MEETING_NOTES_PARENT_ID` on the **FastAPI** `.env`, Station Alpha will `POST /meetings/{id}/notion-recap` after a successful transcript + extraction so a **child page** is created with a short narrative and the extracted action items.
