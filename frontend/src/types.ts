export type MeetingStatus = 'completed' | 'pending' | 'failed'
export type ProcessingStatus = 'not_started' | 'in_progress' | 'processed' | 'failed'
export type ActionItemStatus =
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'ticket_created'
export type Priority = 'low' | 'medium' | 'high' | 'critical'
export type LogStage =
  | 'ingestion'
  | 'transcript_processing'
  | 'extraction'
  | 'assignment'
  | 'notification'
export type LogStatus = 'success' | 'failed' | 'pending' | 'skipped'

export type DashboardWindowDays = 7 | 30

export interface DashboardSummary {
  total_meetings: number
  total_processed_meetings: number
  total_transcripts: number
  total_action_items: number
  total_pending_reviews: number
  total_failed_pipelines: number
  average_processing_time_ms: number | null
  success_rate: number | null
  window_days: DashboardWindowDays
  meetings_in_window: number
  action_items_in_window: number
  pipelines_in_progress: number
  pipelines_not_started: number
  total_participant_seats: number
  avg_action_items_per_meeting: number | null
  avg_transcript_length: number | null
  pending_review_avg_confidence: number | null
  pending_review_low_confidence: number
  action_items_approved_or_ticketed: number
  action_items_rejected: number
  action_items_ticket_created: number
  human_review_throughput_rate: number | null
  meetings_by_processing_status: Record<string, number>
  meetings_by_meeting_status: Record<string, number>
  action_items_by_status: Record<string, number>
}

export interface MeetingListItem {
  id: string
  title: string
  source: string
  date: string
  duration_minutes: number
  status: MeetingStatus
  processing_status: ProcessingStatus
  participants_count: number
  action_items_count: number
  pending_review_count: number
  transcript_length: number | null
}

export interface MeetingsListSummary {
  all_meetings: number
  all_action_items: number
  all_pending_review: number
  all_participant_seats: number
}

export interface MeetingsListPage {
  items: MeetingListItem[]
  total: number
  page: number
  page_size: number
  summary: MeetingsListSummary
}

export interface RelatedLinkOut {
  title: string
  url: string
}

export interface TranscriptSegment {
  speaker: string | null
  text: string
}

export interface TranscriptOut {
  id: string
  meeting_id: string
  raw_text: string
  segments: TranscriptSegment[] | null
  transcript_length: number
  created_at: string
}

export interface ParticipantOut {
  id: string
  display_name: string
  email: string | null
}

export interface MeetingParticipantOut {
  participant: ParticipantOut
  role: string | null
}

export interface ActionItemOut {
  id: string
  meeting_id: string
  description: string
  owner_name: string | null
  due_date: string | null
  priority: Priority
  confidence: number
  status: ActionItemStatus
  source_snippet: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ActionItemReviewOut extends ActionItemOut {
  meeting_title: string
  meeting_start_time: string
}

export interface ProcessingLogOut {
  id: string
  meeting_id: string
  stage: LogStage
  status: LogStatus
  message: string
  processing_time_ms: number | null
  timestamp: string
}

export interface ProcessingLogsPage {
  items: ProcessingLogOut[]
  total: number
  page: number
  page_size: number
}

export interface ReviewQueuePage {
  items: ActionItemReviewOut[]
  page: number
  page_size: number
  total_meetings: number
  total_pending_items: number
}

export interface ActionItemReviewDetailOut extends ActionItemReviewOut {
  participants: MeetingParticipantOut[]
  processing_logs: ProcessingLogOut[]
}

export interface ProjectListItem {
  id: string
  name: string
}

export interface MeetingMetadata {
  id: string
  title: string
  source: string
  start_time: string
  duration_minutes: number
  status: MeetingStatus
  processing_status: ProcessingStatus
  participants_count: number
  project_id: string | null
  project_theme: string | null
  context_developer: string | null
  context_pm: string | null
}

export interface MeetingDetailResponse {
  meeting: MeetingMetadata
  transcript: TranscriptOut | null
  participants: MeetingParticipantOut[]
  action_items: ActionItemOut[]
  processing_logs: ProcessingLogOut[]
  related_links?: RelatedLinkOut[]
}

export interface ActivityLogItem {
  id: string
  action_item_id: string
  meeting_id: string
  meeting_title: string
  action_item_preview: string
  action: string
  status: string
  message: string
  details: Record<string, unknown> | null
  triggered_by: string
  created_at: string
  updated_at: string | null
}

export interface ActivityPage {
  items: ActivityLogItem[]
  total: number
  page: number
  page_size: number
}
