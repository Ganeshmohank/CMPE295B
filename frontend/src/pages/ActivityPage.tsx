import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { ActivityLogItem } from '../types'

const PAGE_SIZE = 20

function statusClass(status: string) {
  if (status === 'success') return 'activity-status activity-status--ok'
  if (status === 'error') return 'activity-status activity-status--err'
  if (status === 'running') return 'activity-status activity-status--run'
  return 'activity-status'
}

export function ActivityPage() {
  const [rows, setRows] = useState<ActivityLogItem[] | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api
      .activity({ page, page_size: PAGE_SIZE })
      .then((d) => {
        if (!alive) return
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
  }, [page])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const to = Math.min(page * PAGE_SIZE, total)

  if (err && !rows) return <div className="error-banner">{err}</div>
  if (!rows) return <p className="muted">Loading activity…</p>

  return (
    <>
      <h1>Activity</h1>
      <p className="page-lead muted">
        Orchestration and automation: Notion, calendar, approvals, and manual triggers. Newest
        first.
      </p>
      {err && <div className="error-banner">{err}</div>}
      <div className="filters activity-filters">
        <span className="toolbar-meta muted">
          {total === 0 ? 'No entries yet' : `Rows ${from}–${to} of ${total}`}
        </span>
        {total > PAGE_SIZE && (
          <span className="activity-pager">
            <button
              type="button"
              className="btn-ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </button>
            <span className="muted">
              Page {page} / {totalPages}
            </span>
            <button
              type="button"
              className="btn-ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
            </button>
          </span>
        )}
      </div>
      <div className="table-wrap">
        <table className="activity-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Source</th>
              <th>Action</th>
              <th>Status</th>
              <th>Meeting</th>
              <th>Action item</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr className="activity-empty">
                <td colSpan={7} className="muted">
                  No activity yet — approve items or trigger orchestration to see entries here.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="activity-row">
                  <td className="activity-ts" data-label="When">
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td data-label="Source">
                    <span className="activity-source">{r.triggered_by}</span>
                  </td>
                  <td className="activity-action" data-label="Action">
                    {r.action.replace(/_/g, ' ')}
                  </td>
                  <td data-label="Status">
                    <span className={statusClass(r.status)}>{r.status}</span>
                  </td>
                  <td data-label="Meeting">
                    <Link to={`/meetings/${encodeURIComponent(r.meeting_id)}`}>
                      {r.meeting_title}
                    </Link>
                  </td>
                  <td data-label="Action item">
                    <Link
                      to={`/action-items/${encodeURIComponent(r.action_item_id)}`}
                      className="activity-preview"
                      title={r.action_item_preview}
                    >
                      {r.action_item_preview}
                    </Link>
                  </td>
                  <td className="activity-msg" data-label="Message">
                    {r.message}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}
