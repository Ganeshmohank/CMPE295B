import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { InitialAvatar } from '../components/InitialAvatar'
import { api } from '../api'
import { notifySummaryStale } from '../lib/summarySync'
import { invalidateMeetingDetailCache } from '../lib/meetingDetailCache'
import { formatPacificDateTimeTz } from '../lib/format'
import type { ActionItemReviewDetailOut } from '../types'

// function priorityClass(p: Priority) {
//   if (p === 'critical') return 'prio prio--critical'
//   if (p === 'high') return 'prio prio--high'
//   if (p === 'medium') return 'prio prio--medium'
//   return 'prio prio--low'
// }

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

// const PRIORITY_OPTIONS: Priority[] = ['critical', 'high', 'medium', 'low']

export function ReviewItemPage() {
  const { itemId } = useParams<{ itemId: string }>()
  const navigate = useNavigate()
  const [item, setItem] = useState<ActionItemReviewDetailOut | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [bulkConfirmKind, setBulkConfirmKind] = useState<'approve' | 'reject' | null>(null)
  const [editDesc, setEditDesc] = useState('')
  // const [editOwner, setEditOwner] = useState('')
  // const [editDue, setEditDue] = useState('')
  // const [editPriority, setEditPriority] = useState<Priority>('medium')

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

  useEffect(() => {
    if (!item) return
    setEditDesc(item.description)
    // setEditOwner(item.owner_name ?? '')
    // setEditDue(item.due_date ? String(item.due_date).slice(0, 10) : '')
    // setEditPriority(item.priority)
  }, [item])

  async function saveEdits() {
    if (!itemId || !item) return
    const mid = item.meeting_id
    setBusy(true)
    setErr(null)
    try {
      await api.patchActionItem(itemId, {
        description: editDesc.trim(),
        // owner_name: editOwner.trim() === '' ? null : editOwner.trim(),
        // due_date: editDue === '' ? null : editDue,
        // priority: editPriority,
      })
      invalidateMeetingDetailCache(mid)
      notifySummaryStale()
      await load()
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e)
      setErr(formatReviewItemLoadError(raw))
    } finally {
      setBusy(false)
    }
  }

  async function runBulk(
    fn: () => Promise<unknown>,
    goTo: 'review' | 'meeting' = 'review',
  ) {
    if (!item) return
    setBusy(true)
    setErr(null)
    try {
      await fn()
      invalidateMeetingDetailCache(item.meeting_id)
      notifySummaryStale()
      if (goTo === 'meeting') {
        navigate(`/meetings/${item.meeting_id}#action-review`, { replace: true })
      } else {
        navigate('/review', { replace: true })
      }
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
      <ConfirmDialog
        open={bulkConfirmKind !== null}
        title={
          bulkConfirmKind === 'reject'
            ? 'Reject all pending items?'
            : 'Approve all pending items?'
        }
        message={
          bulkConfirmKind === 'reject'
            ? 'Every action item still awaiting review for this meeting will be marked rejected.'
            : 'Every action item still awaiting review for this meeting will be marked approved.'
        }
        confirmLabel={bulkConfirmKind === 'reject' ? 'Reject all' : 'Approve all'}
        cancelLabel="Cancel"
        variant={bulkConfirmKind === 'reject' ? 'danger' : 'default'}
        onCancel={() => setBulkConfirmKind(null)}
        onConfirm={() => {
          const kind = bulkConfirmKind
          setBulkConfirmKind(null)
          if (!item) return
          if (kind === 'approve') {
            void runBulk(() => api.bulkApproveMeeting(item.meeting_id), 'review')
          } else if (kind === 'reject') {
            void runBulk(() => api.bulkRejectMeeting(item.meeting_id), 'review')
          }
        }}
      />
      <p className="detail-back">
        <Link to="/review">← Back to review queue</Link>
        {item && (
          <>
            {' · '}
            <Link to={`/review?meeting=${encodeURIComponent(item.meeting_id)}`}>
              Queue for this meeting
            </Link>
          </>
        )}
      </p>
      <div className="page-header">
        <h1>Review action item</h1>
        <p className="page-subtitle muted">
          From{' '}
          <Link to={`/meetings/${item.meeting_id}#action-review`}>{item.meeting_title}</Link>
          {' · '}
          {formatPacificDateTimeTz(item.meeting_start_time)}
          {' · '}
          <Link to={`/review?meeting=${encodeURIComponent(item.meeting_id)}`}>
            This meeting&apos;s review queue
          </Link>
        </p>
      </div>
      {err && <div className="error-banner">{err}</div>}

      <div className="detail-page detail-page--review-item">
        <div className="detail-page__main detail-page__main--review-flow">
          <article className="review-item review-item--solo">
            <div className="review-item__top review-item__top--compact">
              <InitialAvatar name={item.owner_name} />
              <div className="review-item__body">
                <div className="review-item-edit-block">
                  <label className="field-label" htmlFor="rev-item-desc">
                    Description
                  </label>
                  <textarea
                    id="rev-item-desc"
                    className="field-input review-item-edit-block__textarea"
                    rows={3}
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                  />
                  {/*
                  <label className="field-label" htmlFor="rev-item-owner">
                    Owner
                  </label>
                  <input
                    id="rev-item-owner"
                    className="field-input"
                    value={editOwner}
                    onChange={(e) => setEditOwner(e.target.value)}
                  />
                  <label className="field-label" htmlFor="rev-item-due">
                    Due
                  </label>
                  <input
                    id="rev-item-due"
                    className="field-input"
                    type="date"
                    value={editDue}
                    onChange={(e) => setEditDue(e.target.value)}
                  />
                  <label className="field-label" htmlFor="rev-item-prio">
                    Priority
                  </label>
                  <select
                    id="rev-item-prio"
                    className="field-input"
                    value={editPriority}
                    onChange={(e) => setEditPriority(e.target.value as Priority)}
                  >
                    {PRIORITY_OPTIONS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                  */}
                  <button
                    type="button"
                    className="btn btn-ghost btn--sm"
                    disabled={busy}
                    onClick={() => void saveEdits()}
                  >
                    Save changes
                  </button>
                </div>
                <p className="review-item__confidence-line muted">
                  Model confidence: {(item.confidence * 100).toFixed(0)}%
                </p>
              </div>
            </div>
            {item.source_snippet && (
              <blockquote className="review-item__quote">
                <span className="review-item__quote-label">Transcript context</span>
                {item.source_snippet}
              </blockquote>
            )}
            <div className="review-item__footer review-item__footer--solo review-item__footer--bulk">
              <p className="muted review-item__bulk-hint">
                Approve or reject <strong>all pending</strong> items for this meeting at once (not only
                this row).
              </p>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => setBulkConfirmKind('approve')}
              >
                Approve all in meeting
              </button>
              <button
                type="button"
                className="btn btn-ghost btn--danger-outline"
                disabled={busy}
                onClick={() => setBulkConfirmKind('reject')}
              >
                Reject all in meeting
              </button>
              <Link
                className="btn btn-ghost"
                to={`/meetings/${item.meeting_id}#action-review`}
              >
                Back to meeting
              </Link>
            </div>
          </article>

          <section className="review-participants-inline panel panel--elevated" aria-label="Meeting participants">
            <h3 className="panel__h review-participants-inline__h">Participants</h3>
            {item.participants.length === 0 ? (
              <p className="muted">No participants linked.</p>
            ) : (
              <>
                <div className="avatar-stack review-participants-inline__avatars">
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
                <ul className="review-participants-inline__names">
                  {item.participants.map((p) => (
                    <li key={p.participant.id}>
                      <span className="review-participants-inline__n">{p.participant.display_name}</span>
                      {p.participant.email && (
                        <span className="review-participants-inline__e muted">{p.participant.email}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>

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
                        <td>{formatPacificDateTimeTz(l.timestamp)}</td>
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
      </div>
    </>
  )
}
