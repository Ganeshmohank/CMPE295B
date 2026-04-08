import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { fmtChars, relativeTime } from '../lib/format'
import type { MeetingListItem, MeetingStatus, MeetingsListPage, ProcessingStatus } from '../types'

const VALID_PIPELINE = new Set<ProcessingStatus>([
  'processed',
  'in_progress',
  'not_started',
  'failed',
])

const PAGE_SIZE = 10

function procPill(s: ProcessingStatus) {
  if (s === 'processed') return 'pill pill-ok'
  if (s === 'failed') return 'pill pill-bad'
  if (s === 'in_progress') return 'pill pill-warn'
  return 'pill pill-neutral'
}

function procLabel(s: ProcessingStatus) {
  if (s === 'in_progress') return 'ongoing'
  return s.replace(/_/g, ' ')
}

function meetPill(s: MeetingStatus) {
  if (s === 'completed') return 'pill pill-ok'
  if (s === 'failed') return 'pill pill-bad'
  return 'pill pill-warn'
}

function meetLabel(s: MeetingStatus) {
  if (s === 'pending') return 'live'
  return s
}

function priorityTone(p: ProcessingStatus) {
  if (p === 'failed') return 'meeting-card meeting-card--alert'
  if (p === 'in_progress' || p === 'not_started') return 'meeting-card meeting-card--warm'
  return 'meeting-card'
}

function parsePipeline(s: string | null): ProcessingStatus | 'all' {
  if (!s || !VALID_PIPELINE.has(s as ProcessingStatus)) return 'all'
  return s as ProcessingStatus
}

type SortKey = 'date_desc' | 'date_asc' | 'pending_first' | 'title' | 'actions_desc'

function sortToApi(s: SortKey): string {
  if (s === 'actions_desc') return 'actions_desc'
  if (s === 'pending_first') return 'pending_first'
  if (s === 'date_asc') return 'date_asc'
  if (s === 'title') return 'title'
  return 'date_desc'
}

export function MeetingsList() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [pageData, setPageData] = useState<MeetingsListPage | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [procFilter, setProcFilter] = useState<ProcessingStatus | 'all'>(() =>
    parsePipeline(searchParams.get('pipeline')),
  )
  const [sort, setSort] = useState<SortKey>(() =>
    searchParams.get('sort')?.trim() === 'actions' ? 'actions_desc' : 'date_desc',
  )
  const [focusPending, setFocusPending] = useState(
    () => searchParams.get('focus')?.trim() === 'pending',
  )

  const page = useMemo(() => {
    const p = parseInt(searchParams.get('page') || '1', 10)
    return Number.isFinite(p) && p >= 1 ? p : 1
  }, [searchParams])

  /** Query params are the source of truth for the API (avoids state lag on load / client navigation). */
  const procFilterForFetch = useMemo(
    () => parsePipeline(searchParams.get('pipeline')),
    [searchParams],
  )
  const focusPendingForFetch = useMemo(
    () => searchParams.get('focus')?.trim() === 'pending',
    [searchParams],
  )
  const sortKeyForFetch = useMemo((): SortKey => {
    if (searchParams.get('sort')?.trim() === 'actions') return 'actions_desc'
    return sort
  }, [searchParams, sort])

  const filterKey = `${debouncedQ}|${procFilterForFetch}|${focusPendingForFetch}|${sortKeyForFetch}`
  const prevFilterKey = useRef<string | null>(null)

  useEffect(() => {
    setProcFilter(parsePipeline(searchParams.get('pipeline')))
    if (searchParams.get('sort')?.trim() === 'actions') setSort('actions_desc')
    setFocusPending(searchParams.get('focus')?.trim() === 'pending')
  }, [searchParams])

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(q.trim()), 380)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    if (prevFilterKey.current === null) {
      prevFilterKey.current = filterKey
      return
    }
    if (prevFilterKey.current !== filterKey) {
      prevFilterKey.current = filterKey
      if (searchParams.get('page')) {
        const next = new URLSearchParams(searchParams)
        next.delete('page')
        setSearchParams(next, { replace: true })
      }
    }
  }, [filterKey, searchParams, setSearchParams])

  useEffect(() => {
    let alive = true
    setLoading(true)
    setErr(null)
    api
      .meetings({
        page,
        page_size: PAGE_SIZE,
        q: debouncedQ || undefined,
        pipeline: procFilterForFetch === 'all' ? undefined : procFilterForFetch,
        focus_pending: focusPendingForFetch,
        sort: sortToApi(sortKeyForFetch),
      })
      .then((d) => {
        if (!alive) return
        if (!d) {
          setErr('Invalid meetings response')
          setPageData(null)
          return
        }
        if (d.total > 0 && d.items.length === 0 && d.page > 1) {
          const next = new URLSearchParams(searchParams)
          next.delete('page')
          setSearchParams(next, { replace: true })
          return
        }
        setPageData(d)
      })
      .catch((e: Error) => {
        if (alive) {
          setErr(e.message)
          setPageData(null)
        }
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [
    page,
    debouncedQ,
    procFilterForFetch,
    focusPendingForFetch,
    sortKeyForFetch,
    searchParams,
    setSearchParams,
  ])

  function setPageParam(n: number) {
    const next = new URLSearchParams(searchParams)
    if (n <= 1) next.delete('page')
    else next.set('page', String(n))
    setSearchParams(next, { replace: true })
  }

  function setPipelineParam(v: ProcessingStatus | 'all') {
    setProcFilter(v)
    const next = new URLSearchParams(searchParams)
    if (v === 'all') next.delete('pipeline')
    else next.set('pipeline', v)
    next.delete('page')
    setSearchParams(next, { replace: true })
  }

  function setSortParam(v: SortKey) {
    setSort(v)
    const next = new URLSearchParams(searchParams)
    if (v === 'actions_desc') next.set('sort', 'actions')
    else next.delete('sort')
    next.delete('page')
    setSearchParams(next, { replace: true })
  }

  function setPendingFocusParam(on: boolean) {
    const next = new URLSearchParams(searchParams)
    if (on) next.set('focus', 'pending')
    else next.delete('focus')
    next.delete('page')
    setSearchParams(next, { replace: true })
  }

  function resetListFilters() {
    setQ('')
    setDebouncedQ('')
    setProcFilter('all')
    setSort('date_desc')
    setFocusPending(false)
    setSearchParams({}, { replace: true })
  }

  const summary = pageData?.summary
  const total = pageData?.total ?? 0
  const items: MeetingListItem[] = pageData?.items ?? []
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const rangeFrom = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const rangeTo = Math.min(page * PAGE_SIZE, total)

  if (err) return <div className="error-banner">{err}</div>

  return (
    <>
      <div className="page-header">
        <h1>Meetings</h1>
        <p className="page-subtitle">
          Browse captured sessions, pipeline state, transcript size, and how many action items need
          review. Up to {PAGE_SIZE} rows per page; filters sync with the URL.
        </p>
      </div>

      {(searchParams.has('pipeline') ||
        searchParams.has('sort') ||
        searchParams.get('focus') === 'pending') && (
        <p className="filter-banner muted">
          Filtered view (from dashboard or URL).{' '}
          <button type="button" className="filter-banner__clear filter-banner__clear--btn" onClick={resetListFilters}>
            Clear filters
          </button>
        </p>
      )}

      {summary && (
        <div className="meetings-kpis" aria-label="Meeting list totals — click to filter">
          <button
            type="button"
            className="meetings-kpi meetings-kpi--btn"
            onClick={resetListFilters}
            title="Show all meetings"
          >
            <span className="meetings-kpi__val">{summary.all_meetings}</span>
            <span className="meetings-kpi__lbl">meetings</span>
          </button>
          <button
            type="button"
            className="meetings-kpi meetings-kpi--btn"
            onClick={() => {
              setPendingFocusParam(false)
              setSortParam('actions_desc')
            }}
            title="Sort by most action items"
          >
            <span className="meetings-kpi__val">{summary.all_action_items}</span>
            <span className="meetings-kpi__lbl">action items</span>
          </button>
          <button
            type="button"
            className={
              'meetings-kpi meetings-kpi--btn meetings-kpi--accent' +
              (focusPending ? ' is-active' : '')
            }
            onClick={() => setPendingFocusParam(!focusPending)}
            title="Toggle rows with pending review only"
          >
            <span className="meetings-kpi__val">{summary.all_pending_review}</span>
            <span className="meetings-kpi__lbl">pending review</span>
          </button>
          <div className="meetings-kpi meetings-kpi--quiet" title="Sum of participants_count (informational)">
            <span className="meetings-kpi__val">{summary.all_participant_seats}</span>
            <span className="meetings-kpi__lbl">participant seats</span>
          </div>
        </div>
      )}

      <div className="toolbar">
        <input
          type="search"
          className="input-search"
          placeholder="Search title or source…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search meetings"
        />
        <select
          className="select-mini"
          value={procFilter}
          onChange={(e) =>
            setPipelineParam(e.target.value as ProcessingStatus | 'all')
          }
          aria-label="Filter by pipeline"
        >
          <option value="all">All pipelines</option>
          <option value="processed">Processed</option>
          <option value="in_progress">In progress</option>
          <option value="not_started">Not started</option>
          <option value="failed">Failed</option>
        </select>
        <select
          className="select-mini"
          value={sort}
          onChange={(e) => setSortParam(e.target.value as SortKey)}
          aria-label="Sort meetings"
        >
          <option value="date_desc">Newest first</option>
          <option value="date_asc">Oldest first</option>
          <option value="actions_desc">Most action items</option>
          <option value="pending_first">Most pending review</option>
          <option value="title">Title A–Z</option>
        </select>
        <span className="toolbar-meta">
          {loading ? (
            'Loading…'
          ) : (
            <>
              {total === 0
                ? 'No matches'
                : `Rows ${rangeFrom}–${rangeTo} of ${total} matching`}
            </>
          )}
        </span>
      </div>

      {loading && !pageData ? (
        <p className="muted">Loading meetings…</p>
      ) : (
        <>
          <ul className="meeting-card-list">
            {items.map((m) => (
              <li key={m.id}>
                <article className={priorityTone(m.processing_status)}>
                  <div className="meeting-card__main">
                    <Link to={`/meetings/${m.id}`} className="meeting-card__title">
                      {m.title}
                    </Link>
                    <div className="meeting-card__meta">
                      <span title={new Date(m.date).toLocaleString()}>{relativeTime(m.date)}</span>
                      <span className="dot-sep">·</span>
                      <span>
                        {(m.duration_minutes ?? 0) > 0 ? `${m.duration_minutes} min` : 'Duration —'}
                      </span>
                      <span className="dot-sep">·</span>
                      <span className="source-pill">{m.source}</span>
                    </div>
                  </div>
                  <div className="meeting-card__tags">
                    <span className={meetPill(m.status)}>{meetLabel(m.status)}</span>
                    <span className={procPill(m.processing_status)}>{procLabel(m.processing_status)}</span>
                  </div>
                  <div className="meeting-card__stats">
                    <div className="mini-stat" title="Participants">
                      <span className="mini-stat__n">{m.participants_count ?? 0}</span>
                      <span className="mini-stat__l">people</span>
                    </div>
                    <div className="mini-stat" title="Extracted action items">
                      <span className="mini-stat__n">{m.action_items_count ?? 0}</span>
                      <span className="mini-stat__l">actions</span>
                    </div>
                    <div
                      className={
                        'mini-stat' + ((m.pending_review_count ?? 0) > 0 ? ' mini-stat--pulse' : '')
                      }
                      title="Pending human review"
                    >
                      <span className="mini-stat__n">{m.pending_review_count ?? 0}</span>
                      <span className="mini-stat__l">review</span>
                    </div>
                    <div className="mini-stat" title="Transcript character count">
                      <span className="mini-stat__n">{fmtChars(m.transcript_length)}</span>
                      <span className="mini-stat__l">chars</span>
                    </div>
                  </div>
                </article>
              </li>
            ))}
          </ul>

          {total > 0 && totalPages > 1 && (
            <nav className="pager" aria-label="Meeting pages">
              <button
                type="button"
                className="btn btn-ghost btn--sm"
                disabled={page <= 1 || loading}
                onClick={() => setPageParam(page - 1)}
              >
                Previous
              </button>
              <span className="pager__status muted">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                className="btn btn-ghost btn--sm"
                disabled={page >= totalPages || loading}
                onClick={() => setPageParam(page + 1)}
              >
                Next
              </button>
            </nav>
          )}

          {total === 0 && !loading && (
            <p className="muted empty-hint">No meetings match your filters.</p>
          )}
        </>
      )}
    </>
  )
}
