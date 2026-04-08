import type {
  ActionItemReviewOut,
  ProcessingLogOut,
  ProcessingLogsPage,
  ReviewQueuePage,
} from '../types'

function num(v: unknown, fallback: number): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

/** Best-effort parse for paginated processing logs. */
export function normalizeProcessingLogsPage(raw: unknown): ProcessingLogsPage | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  if (!Array.isArray(r.items)) return null
  const items = r.items as ProcessingLogOut[]
  return {
    items,
    total: Math.max(0, num(r.total, 0)),
    page: Math.max(1, num(r.page, 1)),
    page_size: Math.max(1, num(r.page_size, 10)),
  }
}

/** Best-effort parse for paginated review queue. */
export function normalizeReviewQueuePage(raw: unknown): ReviewQueuePage | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  if (!Array.isArray(r.items)) return null
  const items = r.items as ActionItemReviewOut[]
  return {
    items,
    page: Math.max(1, num(r.page, 1)),
    page_size: Math.max(1, num(r.page_size, 10)),
    total_meetings: Math.max(0, num(r.total_meetings, 0)),
    total_pending_items: Math.max(0, num(r.total_pending_items, 0)),
  }
}
