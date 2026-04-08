import type { DashboardSummary, DashboardWindowDays } from '../types'

/** Coerce API JSON so missing fields never crash the UI (older backends, partial responses). */
export function normalizeDashboardSummary(raw: unknown): DashboardSummary {
  const o =
    raw && typeof raw === 'object' && !Array.isArray(raw)
      ? (raw as Record<string, unknown>)
      : {}
  const n = (v: unknown, d = 0) =>
    typeof v === 'number' && Number.isFinite(v) ? v : d
  const nn = (v: unknown): number | null =>
    typeof v === 'number' && Number.isFinite(v) ? v : null
  const dict = (v: unknown): Record<string, number> => {
    if (!v || typeof v !== 'object' || Array.isArray(v)) return {}
    const out: Record<string, number> = {}
    for (const [k, val] of Object.entries(v)) {
      if (typeof val === 'number' && Number.isFinite(val)) out[k] = val
    }
    return out
  }
  const wd = o.window_days === 30 ? 30 : 7

  return {
    total_meetings: n(o.total_meetings),
    total_processed_meetings: n(o.total_processed_meetings),
    total_transcripts: n(o.total_transcripts),
    total_action_items: n(o.total_action_items),
    total_pending_reviews: n(o.total_pending_reviews),
    total_failed_pipelines: n(o.total_failed_pipelines),
    average_processing_time_ms: nn(o.average_processing_time_ms),
    success_rate: nn(o.success_rate),
    window_days: wd as DashboardWindowDays,
    meetings_in_window: n(o.meetings_in_window),
    action_items_in_window: n(o.action_items_in_window),
    pipelines_in_progress: n(o.pipelines_in_progress),
    pipelines_not_started: n(o.pipelines_not_started),
    total_participant_seats: n(o.total_participant_seats),
    avg_action_items_per_meeting: nn(o.avg_action_items_per_meeting),
    avg_transcript_length: nn(o.avg_transcript_length),
    pending_review_avg_confidence: nn(o.pending_review_avg_confidence),
    pending_review_low_confidence: n(o.pending_review_low_confidence),
    action_items_approved_or_ticketed: n(o.action_items_approved_or_ticketed),
    action_items_rejected: n(o.action_items_rejected),
    action_items_ticket_created: n(o.action_items_ticket_created),
    human_review_throughput_rate: nn(o.human_review_throughput_rate),
    meetings_by_processing_status: dict(o.meetings_by_processing_status),
    meetings_by_meeting_status: dict(o.meetings_by_meeting_status),
    action_items_by_status: dict(o.action_items_by_status),
  }
}
