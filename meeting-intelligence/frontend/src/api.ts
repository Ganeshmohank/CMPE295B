import { normalizeDashboardSummary } from './lib/normalizeDashboardSummary'
import { normalizeMeetingsListPage } from './lib/normalizeMeetingListItem'
import {
  normalizeProcessingLogsPage,
  normalizeReviewQueuePage,
} from './lib/normalizePages'
import type {
  ActionItemOut,
  ActionItemReviewDetailOut,
  DashboardSummary,
  DashboardWindowDays,
  LogStage,
  LogStatus,
  MeetingDetailResponse,
  MeetingMetadata,
  MeetingParticipantOut,
  MeetingsListPage,
  ProcessingLogsPage,
  ProjectListItem,
  ReviewQueuePage,
} from './types'

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  summary: (windowDays: DashboardWindowDays = 7): Promise<DashboardSummary> =>
    json<unknown>(`/api/dashboard/summary?window_days=${windowDays}`).then(
      normalizeDashboardSummary,
    ),
  meetings: (params: {
    page?: number
    page_size?: number
    q?: string
    pipeline?: string
    focus_pending?: boolean
    sort?: string
  }): Promise<MeetingsListPage | null> => {
    const q = new URLSearchParams()
    q.set('page', String(params.page ?? 1))
    q.set('page_size', String(Math.min(10, Math.max(1, params.page_size ?? 10))))
    if (params.q != null && params.q.trim() !== '') q.set('q', params.q.trim())
    if (params.pipeline != null && params.pipeline !== '' && params.pipeline !== 'all') {
      q.set('pipeline', params.pipeline)
    }
    if (params.focus_pending) q.set('focus_pending', 'true')
    if (params.sort != null && params.sort !== '') q.set('sort', params.sort)
    return json<unknown>(`/api/dashboard/meetings?${q}`).then(normalizeMeetingsListPage)
  },
  meetingDetail: (id: string) =>
    json<MeetingDetailResponse>(`/api/meetings/${encodeURIComponent(id)}`),
  projectTeamMembers: (projectId: string) =>
    json<MeetingParticipantOut[]>(
      `/api/projects/${encodeURIComponent(projectId)}/team-members`,
    ),
  addMeetingTeamMember: (
    meetingId: string,
    body: {
      display_name: string
      email?: string | null
      add_to_linked_project?: boolean
    },
  ) =>
    json<MeetingParticipantOut>(`/api/meetings/${encodeURIComponent(meetingId)}/team-members`, {
      method: 'POST',
      body: JSON.stringify({
        display_name: body.display_name,
        email: body.email ?? null,
        add_to_linked_project: body.add_to_linked_project ?? true,
      }),
    }),
  projectsList: () => json<ProjectListItem[]>('/api/projects/catalog'),
  patchMeetingContext: (
    id: string,
    body: {
      project_id?: string | null
      project_theme?: string | null
      context_developer?: string | null
      context_pm?: string | null
    },
  ) =>
    json<MeetingMetadata>(`/api/meetings/${encodeURIComponent(id)}/context`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  /** Distinct project/initiative strings from meetings; optional q filters server-side. */
  projectThemes: (q?: string) => {
    const params = q != null && q.trim() !== '' ? `?q=${encodeURIComponent(q.trim())}` : ''
    return json<{ themes: string[] }>(`/api/dashboard/project-themes${params}`).then((r) => r.themes)
  },
  reviewQueue: (page = 1, pageSize = 10): Promise<ReviewQueuePage | null> =>
    json<unknown>(
      `/api/action-items/review-queue?page=${page}&page_size=${Math.min(10, Math.max(1, pageSize))}`,
    ).then(normalizeReviewQueuePage),
  reviewQueueItem: (itemId: string) =>
    json<ActionItemReviewDetailOut>(
      `/api/action-items/${encodeURIComponent(itemId)}/review-detail`,
    ),
  processingLogs: (params: {
    page?: number
    page_size?: number
    stage?: LogStage
    status?: LogStatus
  }): Promise<ProcessingLogsPage | null> => {
    const q = new URLSearchParams()
    q.set('page', String(params.page ?? 1))
    q.set('page_size', String(Math.min(10, Math.max(1, params.page_size ?? 10))))
    if (params.stage) q.set('stage', params.stage)
    if (params.status) q.set('status', params.status)
    return json<unknown>(`/api/logs/processing?${q}`).then(normalizeProcessingLogsPage)
  },
  approveItem: (id: string) =>
    json<ActionItemOut>(`/api/action-items/${encodeURIComponent(id)}/approve`, {
      method: 'POST',
    }),
  rejectItem: (id: string) =>
    json<ActionItemOut>(`/api/action-items/${encodeURIComponent(id)}/reject`, {
      method: 'POST',
    }),
  bulkApproveMeeting: (meetingId: string) =>
    json<{ updated: number }>(
      `/api/action-items/meetings/${encodeURIComponent(meetingId)}/bulk-approve`,
      { method: 'POST' },
    ),
  bulkRejectMeeting: (meetingId: string) =>
    json<{ updated: number }>(
      `/api/action-items/meetings/${encodeURIComponent(meetingId)}/bulk-reject`,
      { method: 'POST' },
    ),
}
