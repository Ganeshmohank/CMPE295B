import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { InitialAvatar } from '../components/InitialAvatar'
import { api } from '../api'
import { invalidateMeetingDetailCache } from '../lib/meetingDetailCache'
import { notifySummaryStale } from '../lib/summarySync'
import type { ActionItemReviewOut, Priority, ReviewQueuePage as ReviewQueuePageData } from '../types'

const PAGE_SIZE = 10

function priorityClass(p: Priority) {
  if (p === 'critical') return 'prio prio--critical'
  if (p === 'high') return 'prio prio--high'
  if (p === 'medium') return 'prio prio--medium'
  return 'prio prio--low'
}

function confidenceWords(c: number): string {
  if (c >= 0.85) return 'likely reliable'
  if (c >= 0.65) return 'verify details'
  return 'likely needs edits'
}

export function ReviewQueuePage() {
  const [searchParams] = useSearchParams()
  const meetingFilter = searchParams.get('meeting')?.trim() || null
  const [page, setPage] = useState(1)
  const [queue, setQueue] = useState<ReviewQueuePageData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [rejectMeetingId, setRejectMeetingId] = useState<string | null>(null)

  useEffect(() => {
    setPage(1)
  }, [meetingFilter])

  const load = useCallback(async () => {
    let d = await api.reviewQueue(
      meetingFilter ? 1 : page,
      PAGE_SIZE,
      meetingFilter,
    )
    if (!d) throw new Error('Invalid review queue response')
    if (!meetingFilter && d.items.length === 0 && d.total_pending_items > 0 && page > 1) {
      const fix = await api.reviewQueue(1, PAGE_SIZE, null)
      if (!fix) throw new Error('Invalid review queue response')
      d = fix
      setPage(1)
    }
    setQueue(d)
    notifySummaryStale()
  }, [page, meetingFilter])

  useEffect(() => {
    let alive = true
    setErr(null)
    load().catch((e: unknown) => {
      if (alive) setErr(e instanceof Error ? e.message : String(e))
    })
    return () => {
      alive = false
    }
  }, [load])

  const items = queue?.items ?? []

  const byMeeting = useMemo(() => {
    if (!items.length) return []
    const m = new Map<string, ActionItemReviewOut[]>()
    for (const it of items) {
      const list = m.get(it.meeting_id) ?? []
      list.push(it)
      m.set(it.meeting_id, list)
    }
    for (const [, list] of m) {
      list.sort((a, b) => a.confidence - b.confidence)
    }
    return Array.from(m.entries()).sort(
      (a, b) =>
        new Date(b[1][0].meeting_start_time).getTime() -
        new Date(a[1][0].meeting_start_time).getTime(),
    )
  }, [items])

  const totalPages =
    meetingFilter != null
      ? 1
      : queue != null
        ? Math.max(1, Math.ceil(queue.total_meetings / PAGE_SIZE))
        : 1

  async function run(id: string, fn: () => Promise<unknown>, cacheMeetingId?: string) {
    setBusy(id)
    setErr(null)
    try {
      await fn()
      if (cacheMeetingId) invalidateMeetingDetailCache(cacheMeetingId)
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  function openRejectConfirm(meetingId: string) {
    setRejectMeetingId(meetingId)
  }

  if (err && !queue) return <div className="error-banner">{err}</div>
  if (!queue) {
    return (
      <div className="page-header">
        <h1>Review queue</h1>
        <p className="muted">Loading…</p>
      </div>
    )
  }

  return (
    <>
      <ConfirmDialog
        open={rejectMeetingId !== null}
        title="Reject all pending items?"
        message="Every action item still in pending review for this meeting will be marked rejected."
        confirmLabel="Reject all"
        cancelLabel="Cancel"
        variant="danger"
        onCancel={() => setRejectMeetingId(null)}
        onConfirm={() => {
          const mid = rejectMeetingId
          setRejectMeetingId(null)
          if (mid) run(`bulk-r-${mid}`, () => api.bulkRejectMeeting(mid), mid)
        }}
      />
      <div className="page-header page-header--split">
        <div>
          <h1>Review queue</h1>
          <p className="page-subtitle">
            <strong>Task priority</strong> is how important the work is. <strong>Model confidence</strong>{' '}
            is how sure the extractor is. Open a meeting to edit items and approve or reject{' '}
            <strong>all pending items for that meeting at once</strong>. Up to {PAGE_SIZE} meetings per
            page.
          </p>
        </div>
        {queue.total_pending_items > 0 && (
          <div className="review-queue-stat">
            <span className="review-queue-stat__n">{queue.total_pending_items}</span>
            <span className="review-queue-stat__l">
              {meetingFilter ? 'pending for this meeting' : 'items pending review'}
            </span>
          </div>
        )}
      </div>
      {err && <div className="error-banner">{err}</div>}

      {meetingFilter && queue.total_pending_items === 0 ? (
        <div className="empty-queue">
          <h2 className="empty-queue__title">Nothing pending for this meeting</h2>
          <p className="empty-queue__text">
            Either everything is approved/rejected or this meeting has no items in the review queue.
          </p>
          <div className="empty-queue__actions">
            <Link to={`/meetings/${encodeURIComponent(meetingFilter)}`} className="btn btn-ghost empty-queue__btn">
              Open meeting
            </Link>
            <Link to="/review" className="btn btn-primary empty-queue__btn">
              Full review queue
            </Link>
          </div>
        </div>
      ) : queue.total_pending_items === 0 ? (
        <div className="empty-queue">
          <div className="empty-queue__icon" aria-hidden>
            ✓
          </div>
          <h2 className="empty-queue__title">You&apos;re all caught up</h2>
          <p className="empty-queue__text">No action items are waiting in pending review.</p>
          <Link to="/meetings" className="btn btn-primary empty-queue__btn">
            Browse meetings
          </Link>
        </div>
      ) : (
        <>
        {meetingFilter && byMeeting[0] && (
          <p className="review-queue-filter-banner muted">
            Showing review queue for{' '}
            <Link to={`/meetings/${encodeURIComponent(meetingFilter)}`}>
              {byMeeting[0][1][0]?.meeting_title ?? 'this meeting'}
            </Link>
            .{' '}
            <Link to="/review">View all meetings</Link>
          </p>
        )}
        <p className="muted review-queue__page-meta">
          {meetingFilter
            ? `${queue.total_pending_items} item${queue.total_pending_items === 1 ? '' : 's'} pending for this meeting`
            : `Page ${page} of ${totalPages} — ${byMeeting.length} meeting${
                byMeeting.length === 1 ? '' : 's'
              } on this page`}
        </p>
        <div className="review-meetings">
          {byMeeting.map(([meetingId, group]) => {
            const title = group[0]?.meeting_title ?? 'Meeting'
            const when = new Date(group[0].meeting_start_time).toLocaleString(undefined, {
              dateStyle: 'medium',
              timeStyle: 'short',
            })
            return (
              <section key={meetingId} className="review-meeting">
                <header className="review-meeting__head">
                  <div className="review-meeting__titles">
                    <h2 className="review-meeting__name">
                      <Link to={`/meetings/${meetingId}`}>{title}</Link>
                    </h2>
                    <p className="review-meeting__when">{when}</p>
                  </div>
                  <div className="review-meeting__actions">
                    <span className="review-meeting__count">{group.length} in queue</span>
                    <Link
                      to={`/meetings/${meetingId}#action-review`}
                      className="btn btn-ghost btn--sm"
                    >
                      Review in meeting
                    </Link>
                    <div className="review-meeting__bulk-actions">
                      <span className="review-meeting__bulk-label muted">Bulk:</span>
                      <button
                        type="button"
                        className="btn btn-ghost btn--sm"
                        disabled={busy !== null}
                        onClick={() =>
                          run(`bulk-a-${meetingId}`, () => api.bulkApproveMeeting(meetingId), meetingId)
                        }
                      >
                        {busy === `bulk-a-${meetingId}` ? 'Approving...' : 'Approve all'}
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn--sm btn--danger-outline"
                        disabled={busy !== null}
                        onClick={() => openRejectConfirm(meetingId)}
                      >
                        Reject all
                      </button>
                    </div>
                  </div>
                </header>
                <ul className="review-item-list">
                  {group.map((it) => (
                    <li key={it.id}>
                      <article className="review-item">
                        <div className="review-item__top">
                          <InitialAvatar name={it.owner_name} />
                          <div className="review-item__body">
                            <p className="review-item__desc">
                              <Link
                                to={`/meetings/${meetingId}#action-item-${it.id}`}
                                className="review-item__desc-link"
                              >
                                {it.description}
                              </Link>
                            </p>
                            <div className="review-item__meta-grid">
                              <div className="meta-pair">
                                <span className="meta-pair__k">Task priority</span>
                                <span className={priorityClass(it.priority)}>{it.priority}</span>
                              </div>
                              <div className="meta-pair">
                                <span className="meta-pair__k">Model confidence</span>
                                <span className="meta-pair__v">
                                  {(it.confidence * 100).toFixed(0)}% — {confidenceWords(it.confidence)}
                                </span>
                              </div>
                            </div>
                            <div className="review-item__chips">
                              {it.owner_name && (
                                <span className="chip chip--muted">Owner: {it.owner_name}</span>
                              )}
                              {it.due_date && (
                                <span className="chip chip--muted">Due {it.due_date}</span>
                              )}
                            </div>
                          </div>
                          <div className="review-item__score" title="Raw confidence score">
                            <span className="review-item__score-val">
                              {(it.confidence * 100).toFixed(0)}
                            </span>
                            <span className="review-item__score-unit">%</span>
                          </div>
                        </div>
                        {it.source_snippet && (
                          <blockquote className="review-item__quote">
                            <span className="review-item__quote-label">Transcript context</span>
                            {it.source_snippet}
                          </blockquote>
                        )}
                        <div className="review-item__meter" aria-hidden>
                          <div
                            className="review-item__meter-fill"
                            style={{ width: `${Math.round(it.confidence * 100)}%` }}
                          />
                        </div>
                        <div className="review-item__footer">
                          <div className="review-item__actions">
                            <button
                              type="button"
                              className="btn btn-primary btn--sm"
                              disabled={busy !== null}
                              onClick={() =>
                                run(`approve-${it.id}`, () => api.approveItem(it.id), meetingId)
                              }
                            >
                              {busy === `approve-${it.id}` ? 'Approving...' : 'Approve'}
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn--sm btn--danger-outline"
                              disabled={busy !== null}
                              onClick={() =>
                                run(`reject-${it.id}`, () => api.rejectItem(it.id), meetingId)
                              }
                            >
                              {busy === `reject-${it.id}` ? 'Rejecting...' : 'Reject'}
                            </button>
                          </div>
                          <div className="review-item__links muted">
                            <Link to={`/action-items/${it.id}`} className="review-item__inline-link">
                              Open detail
                            </Link>
                            <span aria-hidden> · </span>
                            <Link to={`/meetings/${meetingId}#action-item-${it.id}`} className="review-item__inline-link">
                              View in meeting
                            </Link>
                          </div>
                        </div>
                      </article>
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
        {!meetingFilter && totalPages > 1 && (
          <nav className="pager" aria-label="Review queue pages">
            <button
              type="button"
              className="btn btn-ghost btn--sm"
              disabled={page <= 1 || busy !== null}
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
              disabled={page >= totalPages || busy !== null}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </nav>
        )}
        </>
      )}
    </>
  )
}
