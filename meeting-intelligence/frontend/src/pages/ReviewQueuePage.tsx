import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { InitialAvatar } from '../components/InitialAvatar'
import { api } from '../api'
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
  const [page, setPage] = useState(1)
  const [queue, setQueue] = useState<ReviewQueuePageData | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    let d = await api.reviewQueue(page, PAGE_SIZE)
    if (!d) throw new Error('Invalid review queue response')
    if (d.items.length === 0 && d.total_pending_items > 0 && page > 1) {
      const fix = await api.reviewQueue(1, PAGE_SIZE)
      if (!fix) throw new Error('Invalid review queue response')
      d = fix
      setPage(1)
    }
    setQueue(d)
    notifySummaryStale()
  }, [page])

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
    queue != null ? Math.max(1, Math.ceil(queue.total_meetings / PAGE_SIZE)) : 1

  async function run(id: string, fn: () => Promise<unknown>) {
    setBusy(id)
    setErr(null)
    try {
      await fn()
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  function bulkReject(meetingId: string) {
    if (!window.confirm('Reject all pending items for this meeting?')) return
    run(`bulk-r-${meetingId}`, () => api.bulkRejectMeeting(meetingId))
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
      <div className="page-header page-header--split">
        <div>
          <h1>Review queue</h1>
          <p className="page-subtitle">
            <strong>Task priority</strong> is how important the work is. <strong>Model confidence</strong>{' '}
            is how sure the extractor is — low scores may need a closer look. Approve or reject each
            item; descriptions are read-only from extraction. Up to {PAGE_SIZE} meetings per page.
          </p>
        </div>
        {queue.total_pending_items > 0 && (
          <div className="review-queue-stat">
            <span className="review-queue-stat__n">{queue.total_pending_items}</span>
            <span className="review-queue-stat__l">items pending review</span>
          </div>
        )}
      </div>
      {err && <div className="error-banner">{err}</div>}

      {queue.total_pending_items === 0 ? (
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
        <p className="muted review-queue__page-meta">
          Page {page} of {totalPages} — {byMeeting.length} meeting
          {byMeeting.length === 1 ? '' : 's'} on this page
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
                    <button
                      type="button"
                      className="btn btn-primary btn--sm"
                      disabled={busy !== null}
                      onClick={() =>
                        run(`bulk-a-${meetingId}`, () => api.bulkApproveMeeting(meetingId))
                      }
                    >
                      Approve all
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn--sm btn--danger-outline"
                      disabled={busy !== null}
                      onClick={() => bulkReject(meetingId)}
                    >
                      Reject all
                    </button>
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
                                to={`/review/item/${it.id}`}
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
                          <button
                            type="button"
                            className="btn btn-primary btn--sm"
                            disabled={busy !== null}
                            onClick={() => run(`ap-${it.id}`, () => api.approveItem(it.id))}
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            className="btn btn-ghost btn--sm"
                            disabled={busy !== null}
                            onClick={() => run(`rj-${it.id}`, () => api.rejectItem(it.id))}
                          >
                            Reject
                          </button>
                        </div>
                      </article>
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
        {totalPages > 1 && (
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
