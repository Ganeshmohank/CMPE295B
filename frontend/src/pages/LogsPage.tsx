import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { APP_TIMEZONE, formatPacificDateTimeTz } from '../lib/format'
import type { LogStage, LogStatus, ProcessingLogOut } from '../types'

const PAGE_SIZE = 10

const STAGE_OPTIONS: { value: LogStage | ''; label: string }[] = [
  { value: '', label: 'All stages' },
  { value: 'ingestion', label: 'Ingestion' },
  { value: 'transcript_processing', label: 'Transcript processing' },
  { value: 'extraction', label: 'Extraction' },
  { value: 'assignment', label: 'Assignment' },
  { value: 'notification', label: 'Notification' },
  { value: 'notion_recap', label: 'Notion recap' },
]

const STATUS_OPTIONS: { value: LogStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'success', label: 'Success' },
  { value: 'failed', label: 'Failed' },
  { value: 'pending', label: 'Pending' },
  { value: 'skipped', label: 'Skipped' },
]

export function LogsPage() {
  const [rows, setRows] = useState<ProcessingLogOut[] | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [err, setErr] = useState<string | null>(null)
  const [stage, setStage] = useState<LogStage | ''>('')
  const [status, setStatus] = useState<LogStatus | ''>('')
  const [meetingIdFilter, setMeetingIdFilter] = useState('')
  const [messageInput, setMessageInput] = useState('')
  const [messageQ, setMessageQ] = useState('')

  useEffect(() => {
    const t = window.setTimeout(() => setMessageQ(messageInput.trim()), 400)
    return () => window.clearTimeout(t)
  }, [messageInput])

  useEffect(() => {
    setPage(1)
  }, [stage, status, meetingIdFilter, messageQ])

  useEffect(() => {
    let alive = true
    api
      .processingLogs({
        page,
        page_size: PAGE_SIZE,
        stage: stage || undefined,
        status: status || undefined,
        meeting_id: meetingIdFilter.trim() || undefined,
        q: messageQ || undefined,
      })
      .then((d) => {
        if (!alive) return
        if (!d) {
          setErr('Invalid logs response')
          setRows(null)
          return
        }
        if (d.total > 0 && d.items.length === 0 && d.page > 1) {
          setPage(1)
          return
        }
        setRows(d.items)
        setTotal(d.total)
        setErr(null)
      })
      .catch((e: Error) => {
        if (alive) setErr(e.message)
      })
    return () => {
      alive = false
    }
  }, [page, stage, status, meetingIdFilter, messageQ])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const to = Math.min(page * PAGE_SIZE, total)

  if (err && !rows) return <div className="error-banner">{err}</div>
  if (!rows) return <p className="muted">Loading logs…</p>

  return (
    <>
      <h1>Processing logs</h1>
      <p className="page-lead muted">
        Timestamps use <strong>{APP_TIMEZONE}</strong> (Pacific time, PDT/PST).
      </p>
      {err && <div className="error-banner">{err}</div>}
      <div className="filters logs-filters">
        <label>
          Stage{' '}
          <select value={stage} onChange={(e) => setStage(e.target.value as LogStage | '')}>
            {STAGE_OPTIONS.map((o) => (
              <option key={o.value || 'all'} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status{' '}
          <select value={status} onChange={(e) => setStatus(e.target.value as LogStatus | '')}>
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value || 'all'} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="logs-filters__meeting">
          Meeting id{' '}
          <input
            type="text"
            className="logs-filters__input"
            placeholder="Mongo ObjectId…"
            value={meetingIdFilter}
            onChange={(e) => setMeetingIdFilter(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <label className="logs-filters__message">
          Message contains{' '}
          <input
            type="search"
            className="logs-filters__input"
            placeholder="e.g. Notion, 429…"
            value={messageInput}
            onChange={(e) => setMessageInput(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <span className="toolbar-meta muted">
          {total === 0 ? 'No rows' : `Rows ${from}–${to} of ${total}`}
        </span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Timestamp (Pacific)</th>
              <th>Meeting</th>
              <th>Stage</th>
              <th>Status</th>
              <th>Message</th>
              <th>Ms</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((l) => (
              <tr key={l.id}>
                <td className="log-ts">{formatPacificDateTimeTz(l.timestamp)}</td>
                <td>
                  <Link to={`/meetings/${l.meeting_id}`}>open</Link>
                </td>
                <td>{l.stage}</td>
                <td>{l.status}</td>
                <td>{l.message}</td>
                <td>{l.processing_time_ms ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > 0 && totalPages > 1 && (
        <nav className="pager" aria-label="Log pages">
          <button
            type="button"
            className="btn btn-ghost btn--sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </button>
          <span className="pager__status muted">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn--sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </nav>
      )}
    </>
  )
}
