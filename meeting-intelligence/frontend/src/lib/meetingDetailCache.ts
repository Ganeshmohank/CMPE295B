import type { MeetingDetailResponse, MeetingParticipantOut } from '../types'

/** How long a cached meeting detail is treated as fresh (no refetch on revisit). */
const DETAIL_TTL_MS = 3 * 60 * 1000
/** Project roster list, same session / tab. */
const ROSTER_TTL_MS = 3 * 60 * 1000
const MAX_DETAIL_KEYS = 48
const MAX_ROSTER_KEYS = 32

type DetailEntry = { data: MeetingDetailResponse; storedAt: number }
type RosterEntry = { rows: MeetingParticipantOut[]; storedAt: number }

const detailById = new Map<string, DetailEntry>()
const rosterByProjectId = new Map<string, RosterEntry>()

function trimMap<K>(m: Map<K, unknown>, max: number) {
  while (m.size > max) {
    const first = m.keys().next().value
    if (first === undefined) break
    m.delete(first)
  }
}

export function readMeetingDetailCache(meetingId: string): MeetingDetailResponse | null {
  const e = detailById.get(meetingId)
  if (!e) return null
  if (Date.now() - e.storedAt > DETAIL_TTL_MS) {
    detailById.delete(meetingId)
    return null
  }
  return e.data
}

export function writeMeetingDetailCache(meetingId: string, data: MeetingDetailResponse) {
  detailById.delete(meetingId)
  detailById.set(meetingId, { data, storedAt: Date.now() })
  trimMap(detailById, MAX_DETAIL_KEYS)
}

export function invalidateMeetingDetailCache(meetingId?: string) {
  if (meetingId) detailById.delete(meetingId)
  else detailById.clear()
}

export function readProjectRosterCache(projectId: string): MeetingParticipantOut[] | null {
  const e = rosterByProjectId.get(projectId)
  if (!e) return null
  if (Date.now() - e.storedAt > ROSTER_TTL_MS) {
    rosterByProjectId.delete(projectId)
    return null
  }
  return e.rows
}

export function writeProjectRosterCache(projectId: string, rows: MeetingParticipantOut[]) {
  rosterByProjectId.delete(projectId)
  rosterByProjectId.set(projectId, { rows, storedAt: Date.now() })
  trimMap(rosterByProjectId, MAX_ROSTER_KEYS)
}

export function invalidateProjectRosterCache(projectId?: string) {
  if (projectId) rosterByProjectId.delete(projectId)
  else rosterByProjectId.clear()
}
