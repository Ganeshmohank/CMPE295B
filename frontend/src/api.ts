import { normalizeDashboardSummary } from './lib/normalizeDashboardSummary'
import { normalizeMeetingsListPage } from './lib/normalizeMeetingListItem'
import {
  normalizeProcessingLogsPage,
  normalizeReviewQueuePage,
} from './lib/normalizePages'
import type {
  ActionItemOut,
  ActionItemReviewDetailOut,
  ActionItemStatus,
  DashboardSummary,
  DashboardWindowDays,
  LogStage,
  LogStatus,
  MeetingDetailResponse,
  MeetingMetadata,
  MeetingNotionRecapResponse,
  MeetingParticipantOut,
  MeetingsListPage,
  Priority,
  ProcessingLogsPage,
  ProjectListItem,
  ReviewQueuePage,
  ActivityPage,
} from './types'

/** Production: set VITE_API_BASE_URL=https://your-api.example.com (no trailing slash). Dev: leave unset to use Vite proxy. */
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

function apiUrl(path: string): string {
  if (path.startsWith('http')) return path
  return `${API_BASE}${path}`
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
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
  postNotionMeetingRecap: (meetingId: string, body?: { force?: boolean }) =>
    json<MeetingNotionRecapResponse>(
      `/api/meetings/${encodeURIComponent(meetingId)}/notion-recap`,
      {
        method: 'POST',
        body: JSON.stringify(body ?? { force: false }),
      },
    ),
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
  reviewQueue: (
    page = 1,
    pageSize = 10,
    meetingId?: string | null,
  ): Promise<ReviewQueuePage | null> => {
    const q = new URLSearchParams()
    q.set('page', String(page))
    q.set('page_size', String(Math.min(10, Math.max(1, pageSize))))
    if (meetingId != null && meetingId.trim() !== '') {
      q.set('meeting_id', meetingId.trim())
    }
    return json<unknown>(`/api/action-items/review-queue?${q}`).then(normalizeReviewQueuePage)
  },
  reviewQueueItem: (itemId: string) =>
    json<ActionItemReviewDetailOut>(
      `/api/action-items/${encodeURIComponent(itemId)}/review-detail`,
    ),
  actionItemDetail: (itemId: string) =>
    json<ActionItemReviewDetailOut & { project_theme?: string | null }>(
      `/api/action-items/${encodeURIComponent(itemId)}/detail`,
    ),
  processingLogs: (params: {
    page?: number
    page_size?: number
    stage?: LogStage
    status?: LogStatus
    meeting_id?: string
    q?: string
  }): Promise<ProcessingLogsPage | null> => {
    const sp = new URLSearchParams()
    sp.set('page', String(params.page ?? 1))
    sp.set('page_size', String(Math.min(10, Math.max(1, params.page_size ?? 10))))
    if (params.stage) sp.set('stage', params.stage)
    if (params.status) sp.set('status', params.status)
    if (params.meeting_id?.trim()) sp.set('meeting_id', params.meeting_id.trim())
    if (params.q?.trim()) sp.set('q', params.q.trim())
    return json<unknown>(`/api/logs/processing?${sp}`).then(normalizeProcessingLogsPage)
  },
  activity: (params?: { page?: number; page_size?: number }): Promise<ActivityPage> => {
    const q = new URLSearchParams()
    q.set('page', String(params?.page ?? 1))
    q.set('page_size', String(Math.min(50, Math.max(1, params?.page_size ?? 20))))
    return json<ActivityPage>(`/api/activity?${q}`)
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
  patchActionItem: (
    itemId: string,
    body: {
      description?: string
      owner_name?: string | null
      due_date?: string | null
      priority?: Priority
      confidence?: number
      source_snippet?: string | null
      status?: ActionItemStatus
    },
  ) =>
    json<ActionItemOut>(`/api/action-items/${encodeURIComponent(itemId)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  patchTranscript: (
    meetingId: string,
    body: { raw_text: string },
  ) =>
    json<{ id: string; meeting_id: string; raw_text: string }>(
      `/api/meetings/${encodeURIComponent(meetingId)}/transcript`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
      },
    ),
  getExecutionLogs: (actionItemId: string) =>
    json<{
      items: Array<{
        id: string
        action_item_id: string
        meeting_id: string
        action: string
        status: string
        message: string
        details: Record<string, unknown> | null
        triggered_by: string
        created_at: string
        updated_at: string | null
      }>
      total: number
    }>(`/api/orchestration/action-items/${encodeURIComponent(actionItemId)}/logs`),
  triggerOrchestration: (
    actionItemId: string,
    action?: string,
    options?: { new_status?: string; ticket_id?: string },
  ) =>
    json<{ triggered: boolean; execution_log_id: string | null; message: string }>(
      `/api/orchestration/action-items/${encodeURIComponent(actionItemId)}/trigger`,
      {
        method: 'POST',
        body: JSON.stringify({
          action: action ?? null,
          new_status: options?.new_status ?? null,
          ticket_id: options?.ticket_id ?? null,
        }),
      },
    ),
  triggerMeetingUpdate: (
    meetingId: string,
    body: {
      title?: string
      push_to_calendar?: boolean
      notify_participants?: boolean
      action_item_id?: string
    },
  ) =>
    json<{ triggered: boolean; execution_log_id: string | null; message: string }>(
      `/api/orchestration/meetings/${encodeURIComponent(meetingId)}/update`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    ),
}
