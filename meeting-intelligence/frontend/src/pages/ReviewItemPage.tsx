import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { InitialAvatar } from '../components/InitialAvatar'
import { api } from '../api'
import { notifySummaryStale } from '../lib/summarySync'
import type { ActionItemReviewDetailOut, Priority } from '../types'

function priorityClass(p: Priority) {
  if (p === 'critical') return 'prio prio--critical'
  if (p === 'high') return 'prio prio--high'
  if (p === 'medium') return 'prio prio--medium'
  return 'prio prio--low'
}

/** Turn API error bodies into clearer copy (generic Not Found = wrong route or old server). */
function formatReviewItemLoadError(raw: string): string {
  let detail: string | undefined
  try {
    const j = JSON.parse(raw) as { detail?: unknown }
    if (typeof j.detail === 'string') detail = j.detail
    else if (j.detail != null) detail = JSON.stringify(j.detail)
  } catch {
    /* not JSON */
  }
  if (detail === 'Not Found') {
    return 'This item could not be loaded. If you just updated the app, restart the API server so it serves GET /api/action-items/{id}/review-detail. Otherwise open the item again from the review queue (IDs change after re-seeding).'
  }
  if (detail === 'Action item not found') {
    return 'No action item with this id exists (stale bookmark or database was re-seeded). Open it from the review queue instead.'
  }
  if (detail === 'Meeting not found') {
    return 'The meeting for this action item is missing from the database. Try re-seeding or pick another item from the review queue.'
  }
  return detail ?? raw
}

export function ReviewItemPage() {
  const { itemId } = useParams<{ itemId: string }>()
  const navigate = useNavigate()
  const [item, setItem] = useState<ActionItemReviewDetailOut | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    if (!itemId) return Promise.resolve()
    setErr(null)
    return api
      .reviewQueueItem(itemId)
      .then(setItem)
      .catch((e: Error) => {
        setItem(null)
        setErr(formatReviewItemLoadError(e.message))
      })
  }, [itemId])

  useEffect(() => {
    void load()
  }, [load])

  async function run(fn: () => Promise<unknown>) {
    setBusy(true)
    setErr(null)
    try {
      await fn()
      notifySummaryStale()
      navigate('/review', { replace: true })
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e)
      setErr(formatReviewItemLoadError(raw))
    } finally {
      setBusy(false)
    }
  }

  if (!itemId) return <p className="muted">Missing item id.</p>
  if (err && !item) return <div className="error-banner">{err}</div>
  if (!item) return <p className="muted">Loading…</p>

  return (
    <>
      <p className="detail-back">
        <Link to="/review">← Back to review queue</Link>
      </p>
      <div className="page-header">
        <h1>Review action item</h1>
        <p className="page-subtitle muted">
          From{' '}
          <Link to={`/meetings/${item.meeting_id}`}>{item.meeting_title}</Link>
          {' · '}
          {new Date(item.meeting_start_time).toLocaleString()}
        </p>
      </div>
      {err && <div className="error-banner">{err}</div>}

      <div className="detail-page">
        <div className="detail-page__main">
          <article className="review-item review-item--solo">
            <div className="review-item__top">
              <InitialAvatar name={item.owner_name} />
              <div className="review-item__body">
                <p className="review-item__desc">{item.description}</p>
                <div className="review-item__meta-grid">
                  <div className="meta-pair">
                    <span className="meta-pair__k">Task priority</span>
                    <span className={priorityClass(item.priority)}>{item.priority}</span>
                  </div>
                  <div className="meta-pair">
                    <span className="meta-pair__k">Model confidence</span>
                    <span className="meta-pair__v">
                      {(item.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                <div className="review-item__chips">
                  {item.owner_name && (
                    <span className="chip chip--muted">Owner: {item.owner_name}</span>
                  )}
                  {item.due_date && (
                    <span className="chip chip--muted">Due {item.due_date}</span>
                  )}
                </div>
              </div>
            </div>
            {item.source_snippet && (
              <blockquote className="review-item__quote">
                <span className="review-item__quote-label">Transcript context</span>
                {item.source_snippet}
              </blockquote>
            )}
            <div className="review-item__footer review-item__footer--solo">
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => run(() => api.approveItem(item.id))}
              >
                Approve
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={busy}
                onClick={() => run(() => api.rejectItem(item.id))}
              >
                Reject
              </button>
            </div>
          </article>

          <div className="panel panel--elevated">
            <h3 className="panel__h">Processing logs</h3>
            {item.processing_logs.length === 0 ? (
              <p className="muted">No processing logs for this meeting.</p>
            ) : (
              <div className="table-wrap table-wrap--plain">
                <table>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Stage</th>
                      <th>Status</th>
                      <th>Message</th>
                      <th>Ms</th>
                    </tr>
                  </thead>
                  <tbody>
                    {item.processing_logs.map((l) => (
                      <tr key={l.id}>
                        <td>{new Date(l.timestamp).toLocaleString()}</td>
                        <td>{l.stage}</td>
                        <td>{l.status}</td>
                        <td>{l.message}</td>
                        <td>{l.processing_time_ms ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <aside className="detail-rail" aria-label="Meeting participants">
          <div className="rail-card">
            <h3 className="rail-card__title">Participants</h3>
            <p className="rail-card__intro muted">Same roster as the meeting detail page.</p>
            {item.participants.length === 0 ? (
              <p className="muted">No participants linked.</p>
            ) : (
              <>
                <div className="avatar-stack">
                  {item.participants.map((p) => (
                    <span
                      key={p.participant.id}
                      className="avatar-stack__item"
                      title={`${p.participant.display_name}${p.participant.email ? ` — ${p.participant.email}` : ''}${p.role ? ` (${p.role})` : ''}`}
                    >
                      <InitialAvatar name={p.participant.display_name} />
                    </span>
                  ))}
                </div>
                <ul className="rail-names">
                  {item.participants.map((p) => (
                    <li key={p.participant.id}>
                      <span className="rail-names__n">{p.participant.display_name}</span>
                      {p.participant.email && (
                        <span className="rail-names__e muted">{p.participant.email}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </aside>
      </div>
    </>
  )
}
