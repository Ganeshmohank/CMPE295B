import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { LogStage, LogStatus, ProcessingLogOut } from '../types'

const PAGE_SIZE = 10

const STAGES: (LogStage | '')[] = [
  '',
  'ingestion',
  'transcript_processing',
  'extraction',
  'assignment',
  'notification',
]

const STATUSES: (LogStatus | '')[] = ['', 'success', 'failed', 'pending', 'skipped']

export function LogsPage() {
  const [rows, setRows] = useState<ProcessingLogOut[] | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [err, setErr] = useState<string | null>(null)
  const [stage, setStage] = useState<LogStage | ''>('')
  const [status, setStatus] = useState<LogStatus | ''>('')

  useEffect(() => {
    setPage(1)
  }, [stage, status])

  useEffect(() => {
    let alive = true
    api
      .processingLogs({
        page,
        page_size: PAGE_SIZE,
        stage: stage || undefined,
        status: status || undefined,
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
  }, [page, stage, status])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const to = Math.min(page * PAGE_SIZE, total)

  if (err && !rows) return <div className="error-banner">{err}</div>
  if (!rows) return <p className="muted">Loading logs…</p>

  return (
    <>
      <h1>Processing logs</h1>
      {err && <div className="error-banner">{err}</div>}
      <div className="filters">
        <label>
          Stage{' '}
          <select
            value={stage}
            onChange={(e) => setStage(e.target.value as LogStage | '')}
          >
            {STAGES.map((s) => (
              <option key={s || 'all'} value={s}>
                {s || 'All'}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status{' '}
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as LogStatus | '')}
          >
            {STATUSES.map((s) => (
              <option key={s || 'all'} value={s}>
                {s || 'All'}
              </option>
            ))}
          </select>
        </label>
        <span className="toolbar-meta muted">
          {total === 0 ? 'No rows' : `Rows ${from}–${to} of ${total}`}
        </span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
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
                <td>{new Date(l.timestamp).toLocaleString()}</td>
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
