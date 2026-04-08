import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BreakdownBars } from '../components/BreakdownBars'
import { api } from '../api'
import { fmtMs, fmtNum, fmtPct } from '../lib/format'
import { notifySummaryStale } from '../lib/summarySync'
import type { DashboardSummary, DashboardWindowDays } from '../types'

const PROC_ORDER = ['not_started', 'in_progress', 'processed', 'failed']
const MEET_ORDER = ['completed', 'pending', 'failed']
const AI_ORDER = ['pending_review', 'approved', 'rejected', 'ticket_created']

export function DashboardHome() {
  const navigate = useNavigate()
  const [windowDays, setWindowDays] = useState<DashboardWindowDays>(7)
  const [data, setData] = useState<DashboardSummary | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setErr(null)
    setLoading(true)
    return api
      .summary(windowDays)
      .then((d) => {
        setData(d)
        notifySummaryStale()
      })
      .catch((e: unknown) =>
        setErr(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setLoading(false))
  }, [windowDays])

  useEffect(() => {
    load()
  }, [load])

  if (err && !data) return <div className="error-banner">{err || 'Request failed'}</div>
  if (loading && !data) {
    return (
      <div className="page-header">
        <h1>Overview</h1>
        <p className="muted">Loading metrics…</p>
        <p className="muted dashboard-load-hint">
          The API runs many database counts in parallel; latency mostly reflects your MongoDB network
          round-trip (e.g. Atlas region vs. your machine), not the UI.
        </p>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="page-header">
        <h1>Overview</h1>
        <p className="muted">No metrics loaded. Try Refresh or check that the API is running.</p>
      </div>
    )
  }

  const heroes: {
    label: string
    value: string
    hint?: string
    onClick: () => void
    aria: string
  }[] = [
    {
      label: 'Meetings captured',
      value: String(data.total_meetings),
      hint: 'All time — open full library',
      onClick: () => navigate('/meetings'),
      aria: 'View all meetings',
    },
    {
      label: 'Fully processed',
      value: String(data.total_processed_meetings),
      hint: `${fmtPct(data.success_rate)} pipeline success`,
      onClick: () => navigate('/meetings?pipeline=processed'),
      aria: 'View meetings with processed pipeline',
    },
    {
      label: 'Awaiting your review',
      value: String(data.total_pending_reviews),
      hint:
        data.pending_review_avg_confidence != null
          ? `Avg model score ${fmtNum(data.pending_review_avg_confidence * 100, 0)}%`
          : 'Human in the loop queue',
      onClick: () => navigate('/meetings?focus=pending'),
      aria: 'View meetings with pending review items',
    },
    {
      label: 'Action items extracted',
      value: String(data.total_action_items),
      hint:
        data.avg_action_items_per_meeting != null
          ? `${fmtNum(data.avg_action_items_per_meeting, 2)} per meeting`
          : undefined,
      onClick: () => navigate('/meetings?sort=actions'),
      aria: 'View meetings sorted by action item count',
    },
  ]

  const secondary: { label: string; value: string; sub?: string; onClick?: () => void }[] = [
    {
      label: `Meetings (${data.window_days}d window)`,
      value: String(data.meetings_in_window),
      sub: 'Started in selected period',
      onClick: () => navigate('/meetings'),
    },
    {
      label: 'Action items (same window)',
      value: String(data.action_items_in_window),
      sub: 'Items from meetings in window',
    },
    {
      label: 'Low-confidence queue',
      value: String(data.pending_review_low_confidence),
      sub: 'Pending & score under 65%',
      onClick: () => navigate('/review'),
    },
    {
      label: 'Tickets created',
      value: String(data.action_items_ticket_created),
      sub: 'From reviewed / approved flow',
    },
    {
      label: 'In progress pipelines',
      value: String(data.pipelines_in_progress),
      onClick: () => navigate('/meetings?pipeline=in_progress'),
    },
    {
      label: 'Not started',
      value: String(data.pipelines_not_started),
      onClick: () => navigate('/meetings?pipeline=not_started'),
    },
    {
      label: 'Failed pipelines',
      value: String(data.total_failed_pipelines),
      onClick: () => navigate('/meetings?pipeline=failed'),
    },
    { label: 'Transcripts stored', value: String(data.total_transcripts) },
    {
      label: 'Avg transcript size',
      value:
        data.avg_transcript_length != null
          ? `${Math.round(data.avg_transcript_length).toLocaleString()} chars`
          : '—',
    },
    {
      label: 'Participant seats (sum)',
      value: (data.total_participant_seats ?? 0).toLocaleString(),
    },
    { label: 'Avg log stage time', value: fmtMs(data.average_processing_time_ms) },
    {
      label: 'Review approval rate',
      value: fmtPct(data.human_review_throughput_rate),
      sub: `${data.action_items_approved_or_ticketed} ok · ${data.action_items_rejected} rejected`,
    },
  ]

  return (
    <>
      <div className="page-header page-header--split">
        <div>
          <h1>Overview</h1>
          <p className="page-subtitle">
            Click a headline metric to open the filtered meetings list or review queue. Counts are
            live from MongoDB.
          </p>
        </div>
        <div className="page-header__actions">
          <div className="segmented" role="group" aria-label="Time window for period metrics">
            <button
              type="button"
              className={windowDays === 7 ? 'segmented__btn is-on' : 'segmented__btn'}
              onClick={() => setWindowDays(7)}
            >
              Last 7 days
            </button>
            <button
              type="button"
              className={windowDays === 30 ? 'segmented__btn is-on' : 'segmented__btn'}
              onClick={() => setWindowDays(30)}
            >
              Last 30 days
            </button>
          </div>
          <button type="button" className="btn btn-ghost btn-refresh" onClick={() => load()}>
            Refresh
          </button>
        </div>
      </div>
      {err && <div className="error-banner">{err}</div>}

      <section className="hero-metrics" aria-label="Key metrics">
        {heroes.map((s) => (
          <button
            key={s.label}
            type="button"
            className="hero-metric hero-metric--click"
            onClick={s.onClick}
            aria-label={s.aria}
          >
            <div className="hero-metric__label">{s.label}</div>
            <div className="hero-metric__value">{s.value}</div>
            {s.hint && <div className="hero-metric__hint">{s.hint}</div>}
            <div className="hero-metric__cta">Open →</div>
          </button>
        ))}
      </section>

      <h2 className="section-title">Volume &amp; throughput</h2>
      <div className="grid-stats grid-stats--dense">
        {secondary.map((s) => (
          <div key={s.label}>
            {s.onClick ? (
              <button
                type="button"
                className="stat-card stat-card--quiet stat-card--click"
                onClick={s.onClick}
              >
                <div className="stat-label">{s.label}</div>
                <div className="stat-value stat-value--sm">{s.value}</div>
                {s.sub != null && s.sub !== '' && <div className="stat-sub">{s.sub}</div>}
              </button>
            ) : (
              <div className="stat-card stat-card--quiet">
                <div className="stat-label">{s.label}</div>
                <div className="stat-value stat-value--sm">{s.value}</div>
                {s.sub != null && s.sub !== '' && <div className="stat-sub">{s.sub}</div>}
              </div>
            )}
          </div>
        ))}
      </div>

      <h2 className="section-title">Composition</h2>
      <div className="breakdown-grid">
        <BreakdownBars
          title="Meetings by pipeline state"
          data={data.meetings_by_processing_status}
          order={PROC_ORDER}
        />
        <BreakdownBars
          title="Meetings by calendar status"
          data={data.meetings_by_meeting_status}
          order={MEET_ORDER}
        />
        <BreakdownBars
          title="Action items by status"
          data={data.action_items_by_status}
          order={AI_ORDER}
        />
      </div>
    </>
  )
}
