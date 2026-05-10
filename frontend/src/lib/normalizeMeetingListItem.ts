import type {
  MeetingListItem,
  MeetingStatus,
  MeetingsListPage,
  ProcessingStatus,
} from '../types'

function toInt(v: unknown): number {
  if (typeof v === 'number' && Number.isFinite(v)) return Math.trunc(v)
  if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) return parseInt(v, 10)
  return 0
}

function toIntOrNull(v: unknown): number | null {
  if (v == null) return null
  if (typeof v === 'number' && Number.isFinite(v)) return Math.trunc(v)
  if (typeof v === 'string' && /^\d+$/.test(v)) return parseInt(v, 10)
  try {
    const x = Number(v)
    if (Number.isFinite(x)) return Math.trunc(x)
  } catch {
    /* ignore */
  }
  return null
}

export function normalizeMeetingListItem(raw: unknown): MeetingListItem | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  const id = r.id
  if (typeof id !== 'string') return null
  return {
    id,
    title: typeof r.title === 'string' ? r.title : '',
    source: typeof r.source === 'string' ? r.source : 'zoom',
    date: typeof r.date === 'string' ? r.date : new Date(0).toISOString(),
    duration_minutes: toInt(r.duration_minutes),
    status: (typeof r.status === 'string' ? r.status : 'pending') as MeetingStatus,
    processing_status: (typeof r.processing_status === 'string'
      ? r.processing_status
      : 'not_started') as ProcessingStatus,
    participants_count: toInt(r.participants_count),
    action_items_count: toInt(r.action_items_count),
    pending_review_count: toInt(r.pending_review_count),
    transcript_length: toIntOrNull(r.transcript_length),
    archived: r.archived === true,
  }
}

export function normalizeMeetingList(raw: unknown): MeetingListItem[] {
  if (!Array.isArray(raw)) return []
  return raw.map(normalizeMeetingListItem).filter((x): x is MeetingListItem => x != null)
}

function toSummary(raw: unknown): MeetingsListPage['summary'] | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const s = raw as Record<string, unknown>
  return {
    all_meetings: toInt(s.all_meetings),
    all_action_items: toInt(s.all_action_items),
    all_pending_review: toInt(s.all_pending_review),
    all_participant_seats: toInt(s.all_participant_seats),
  }
}

export function normalizeMeetingsListPage(raw: unknown): MeetingsListPage | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  const itemsRaw = r.items
  if (!Array.isArray(itemsRaw)) return null
  const items = itemsRaw
    .map(normalizeMeetingListItem)
    .filter((x): x is MeetingListItem => x != null)
  const summary = toSummary(r.summary)
  if (!summary) return null
  return {
    items,
    total: toInt(r.total),
    page: Math.max(1, toInt(r.page)),
    page_size: Math.max(1, toInt(r.page_size)),
    summary,
  }
}
