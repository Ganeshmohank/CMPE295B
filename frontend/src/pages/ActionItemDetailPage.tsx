import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { invalidateMeetingDetailCache } from '../lib/meetingDetailCache'
import { notifySummaryStale } from '../lib/summarySync'
import type { ActionItemOut, ActionItemStatus, Priority } from '../types'

const PACIFIC_TZ = 'America/Los_Angeles'

function formatPacific(iso: string | null | undefined): string {
  if (iso == null || iso === '') return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('en-US', {
    timeZone: PACIFIC_TZ,
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(d)
}

/** Execution trail: time in Pacific with zone abbreviation (PST/PDT). */
function formatPacificLogTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return new Intl.DateTimeFormat('en-US', {
    timeZone: PACIFIC_TZ,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
    timeZoneName: 'short',
  }).format(d)
}

interface ExecutionLog {
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
}

function statusLabel(s: ActionItemStatus): string {
  if (s === 'pending_review') return 'Awaiting review'
  if (s === 'approved') return 'Approved'
  if (s === 'rejected') return 'Rejected'
  return 'Ticket created'
}

function statusClass(s: ActionItemStatus): string {
  if (s === 'pending_review') return 'action-item-status action-item-status--pending'
  if (s === 'approved') return 'action-item-status action-item-status--ok'
  if (s === 'ticket_created') return 'action-item-status action-item-status--ok'
  return 'action-item-status action-item-status--muted'
}

function priorityLabel(p: Priority): string {
  return p.charAt(0).toUpperCase() + p.slice(1)
}

function actionLabel(action: string): string {
  const labels: Record<string, string> = {
    create_jira_ticket: 'Create Jira Issue',
    link_to_epic: 'Link to Epic',
    update_confluence: 'Update Documentation',
    create_subtask: 'Create Subtask',
    update_meeting: 'Update Meeting',
    push_to_calendar: 'Push to Calendar',
    create_calendar_event: 'Calendar Invite',
    notify_team: 'Notify Team',
    auto_orchestration: 'Auto-Orchestration',
    update_ticket_status: 'Update Ticket Status',
  }
  return labels[action] || action
}

function triggeredByLabel(triggeredBy: string): string {
  if (triggeredBy === 'approval') return 'On Approval'
  if (triggeredBy === 'manual_retrigger') return 'Re-triggered'
  if (triggeredBy === 'manual') return 'Manual'
  if (triggeredBy === 'scheduled') return 'Scheduled'
  return triggeredBy
}

function strField(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v : undefined
}

function CalendarLogBlock({ details }: { details: Record<string, unknown> }) {
  if (details.kind !== 'calendar_invite') return null

  const title = strField(details.event_title)
  const tz = strField(details.timezone)
  const startLocal = strField(details.start_local_display)
  const endLocal = strField(details.end_local_display)
  const startUtc = strField(details.start_utc)
  const endUtc = strField(details.end_utc)
  const timeHow = strField(details.time_resolution_label)
  const parsedPreview = strField(details.parsed_from_preview)
  const weekendAdjusted = details.weekend_adjusted === true
  const originalStart = strField(details.original_start_iso)
  const inviteSummary = strField(details.invite_summary)
  const inviteMode = strField(details.invite_mode)
  const rosterN =
    typeof details.roster_participants_count === 'number' ? details.roster_participants_count : null
  const attendeeCount =
    typeof details.attendees_count === 'number' ? details.attendees_count : null
  const emails = Array.isArray(details.attendee_emails)
    ? details.attendee_emails.filter((x): x is string => typeof x === 'string')
    : []
  const emailsTruncated = details.attendee_emails_truncated === true
  const link = strField(details.calendar_link)
  const eventId = strField(details.event_id)
  const err = strField(details.error)
  const stage = strField(details.stage)
  const mock = details.mock === true

  return (
    <div className="execution-log__calendar">
      <div className="execution-log__calendar-head">
        <span className="execution-log__calendar-label">Calendar invite</span>
        {mock && (
          <span className="execution-log__detail-chip execution-log__detail-chip--mock">Mock</span>
        )}
        {inviteMode && (
          <span className="execution-log__detail-chip execution-log__detail-chip--calendar-mode">
            {inviteMode}
          </span>
        )}
      </div>
      {err && (
        <p className="execution-log__calendar-error">
          {stage ? `[${stage}] ` : ''}
          {err}
        </p>
      )}
      <dl className="execution-log__dl">
        {title && (
          <>
            <dt>Title</dt>
            <dd>{title}</dd>
          </>
        )}
        {(startLocal || endLocal) && (
          <>
            <dt>When (local)</dt>
            <dd>
              {[startLocal, endLocal].filter(Boolean).join(' → ')}
              {tz ? ` (${tz})` : ''}
            </dd>
          </>
        )}
        {(startUtc || endUtc) && (
          <>
            <dt>When (UTC)</dt>
            <dd>{[startUtc, endUtc].filter(Boolean).join(' → ')}</dd>
          </>
        )}
        {timeHow && (
          <>
            <dt>Time resolved</dt>
            <dd>{timeHow}</dd>
          </>
        )}
        {parsedPreview && (
          <>
            <dt>Parse source</dt>
            <dd className="execution-log__dl-mono">{parsedPreview}</dd>
          </>
        )}
        {weekendAdjusted && originalStart && (
          <>
            <dt>Weekend shift</dt>
            <dd>Moved to Monday (was {originalStart})</dd>
          </>
        )}
        {(attendeeCount !== null || rosterN !== null) && (
          <>
            <dt>Roster</dt>
            <dd>
              {attendeeCount !== null && `${attendeeCount} email(s) on event`}
              {attendeeCount !== null && rosterN !== null && ' · '}
              {rosterN !== null && `${rosterN} participant link(s)`}
            </dd>
          </>
        )}
        {emails.length > 0 && (
          <>
            <dt>Attendees</dt>
            <dd className="execution-log__dl-mono">
              {emails.join(', ')}
              {emailsTruncated ? ' …' : ''}
            </dd>
          </>
        )}
        {inviteSummary && (
          <>
            <dt>Invites</dt>
            <dd>{inviteSummary}</dd>
          </>
        )}
        {eventId && (
          <>
            <dt>Event ID</dt>
            <dd className="execution-log__dl-mono">{eventId}</dd>
          </>
        )}
      </dl>
      {link && (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="execution-log__link execution-log__link--calendar"
        >
          Open in Google Calendar →
        </a>
      )}
    </div>
  )
}

export function ActionItemDetailPage() {
  const { itemId } = useParams<{ itemId: string }>()
  const [item, setItem] = useState<ActionItemOut | null>(null)
  const [meetingTitle, setMeetingTitle] = useState<string>('')
  const [projectTheme, setProjectTheme] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [editDesc, setEditDesc] = useState('')
  const [editDescDirty, setEditDescDirty] = useState(false)
  const [executionLogs, setExecutionLogs] = useState<ExecutionLog[]>([])
  const [logsLoading, setLogsLoading] = useState(false)
  const [orchestratorBusy, setOrchestratorBusy] = useState<string | null>(null)
  const [meetingMcpBusy, setMeetingMcpBusy] = useState(false)

  const loadLogs = useCallback(async () => {
    if (!itemId) return
    setLogsLoading(true)
    try {
      const res = await api.getExecutionLogs(itemId)
      setExecutionLogs(res.items)
    } catch {
      // Silently fail - logs may not exist yet
    } finally {
      setLogsLoading(false)
    }
  }, [itemId])

  const load = useCallback(async () => {
    if (!itemId) return
    setErr(null)
    try {
      const detail = await api.actionItemDetail(itemId)
      setItem(detail)
      setMeetingTitle(detail.meeting_title)
      setProjectTheme((detail as { project_theme?: string | null }).project_theme ?? null)
      setEditDesc(detail.description)
      setEditDescDirty(false)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [itemId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    void loadLogs()
  }, [loadLogs])

  useEffect(() => {
    if (!itemId) return
    const interval = setInterval(() => {
      void loadLogs()
    }, 3000)
    return () => clearInterval(interval)
  }, [itemId, loadLogs])

  async function saveDescription() {
    if (!itemId || !item || !editDescDirty) return
    setSaving(true)
    try {
      await api.patchActionItem(itemId, { description: editDesc.trim() })
      invalidateMeetingDetailCache(item.meeting_id)
      notifySummaryStale()
      setEditDescDirty(false)
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleTriggerAction(action: string) {
    if (!itemId) return
    setOrchestratorBusy(action)
    try {
      await api.triggerOrchestration(itemId, action)
      await loadLogs()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setOrchestratorBusy(null)
    }
  }

  async function handleUpdateTicketStatus(newStatus: string) {
    if (!itemId) return
    setOrchestratorBusy(`status_${newStatus}`)
    try {
      await api.triggerOrchestration(itemId, 'update_ticket_status', { new_status: newStatus })
      await loadLogs()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setOrchestratorBusy(null)
    }
  }

  async function handleRetriggerAll() {
    if (!itemId) return
    setOrchestratorBusy('retrigger')
    try {
      await api.triggerOrchestration(itemId)
      await loadLogs()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setOrchestratorBusy(null)
    }
  }

  async function handleMeetingMcp(action: 'calendar' | 'notify') {
    if (!item) return
    setMeetingMcpBusy(true)
    try {
      await api.triggerMeetingUpdate(item.meeting_id, {
        push_to_calendar: action === 'calendar',
        notify_participants: action === 'notify',
        action_item_id: itemId,
      })
      await loadLogs()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setMeetingMcpBusy(false)
    }
  }

  if (!itemId) return <p className="muted">Missing item id.</p>
  if (err && !item) return <div className="error-banner">{err}</div>
  if (!item) return <p className="muted">Loading...</p>

  const hasRunningLogs = executionLogs.some((l) => l.status === 'running')

  return (
    <div className="action-item-detail">
      <p className="detail-back">
        <Link to={`/meetings/${item.meeting_id}`}>← Back to meeting</Link>
      </p>

      <div className="action-item-detail__header">
        <p className="action-item-detail__id">ID: {itemId?.slice(-8)}</p>
        <h1>Action Item</h1>
        <p className="page-subtitle muted">
          From <Link to={`/meetings/${item.meeting_id}`}>{meetingTitle}</Link>
          {projectTheme && (
            <>
              {' · '}
              <span className="action-item-detail__theme">{projectTheme}</span>
            </>
          )}
        </p>
        <div className="action-item-detail__badges">
          <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
          <span className="action-item-detail__meta">
            Priority: {priorityLabel(item.priority)} · Confidence: {(item.confidence * 100).toFixed(0)}%
          </span>
        </div>
        
        {item.status === 'pending_review' && (
          <div className="action-item-detail__review-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving}
              onClick={async () => {
                setSaving(true)
                try {
                  await api.approveItem(itemId!)
                  await load()
                  await loadLogs()
                } catch (e) {
                  setErr(e instanceof Error ? e.message : String(e))
                } finally {
                  setSaving(false)
                }
              }}
            >
              {saving ? 'Approving...' : 'Approve & Orchestrate'}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn--danger-outline"
              disabled={saving}
              onClick={async () => {
                setSaving(true)
                try {
                  await api.rejectItem(itemId!)
                  await load()
                } catch (e) {
                  setErr(e instanceof Error ? e.message : String(e))
                } finally {
                  setSaving(false)
                }
              }}
            >
              Reject
            </button>
          </div>
        )}
      </div>

      {err && <div className="error-banner">{err}</div>}

      <div className="action-item-detail__grid">
        <div className="action-item-detail__main">
          <section className="action-item-edit-panel">
            <h3 className="action-item-edit-panel__title">Description</h3>
            <div className="action-item-edit-panel__form">
              <textarea
                className="field-input field-input--area"
                rows={4}
                value={editDesc}
                onChange={(e) => {
                  setEditDesc(e.target.value)
                  setEditDescDirty(e.target.value !== item.description)
                }}
              />
              {editDescDirty && (
                <div className="action-item-edit-panel__row">
                  <button
                    type="button"
                    className="btn btn-ghost btn--sm"
                    disabled={saving}
                    onClick={() => {
                      setEditDesc(item.description)
                      setEditDescDirty(false)
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary btn--sm"
                    disabled={saving}
                    onClick={() => void saveDescription()}
                  >
                    {saving ? 'Saving...' : 'Save'}
                  </button>
                </div>
              )}
            </div>
          </section>

          {item.source_snippet && (
            <section className="source-context-panel">
              <h4 className="source-context-panel__title">Transcript Context</h4>
              <blockquote className="source-context-panel__quote">
                {item.source_snippet}
              </blockquote>
            </section>
          )}

          <section className="execution-logs">
            <div className="execution-logs__header">
              <h3 className="execution-logs__title">Execution Trail</h3>
              <span className="execution-logs__count">
                {logsLoading && hasRunningLogs ? 'Updating...' : `${executionLogs.length} entries`}
              </span>
            </div>
            {executionLogs.length === 0 ? (
              <p className="execution-logs__empty">
                No orchestration actions executed yet.
                {item.status === 'approved' && ' Trigger actions using the panel on the right.'}
                {item.status === 'pending_review' && ' Actions will auto-execute when approved.'}
              </p>
            ) : (
              <ul className="execution-logs__list">
                {executionLogs.map((log) => (
                  <li key={log.id} className="execution-log">
                    <div className="execution-log__head">
                      <span className={`execution-log__status execution-log__status--${log.status}`} />
                      <span className="execution-log__action">{actionLabel(log.action)}</span>
                      <span className="execution-log__triggered-by">{triggeredByLabel(log.triggered_by)}</span>
                      <span className="execution-log__time">
                        {formatPacificLogTime(log.created_at)}
                      </span>
                    </div>
                    <p className="execution-log__message">{log.message}</p>
                    {log.details && (
                      <div className="execution-log__details">
                        <CalendarLogBlock details={log.details} />
                        <div className="execution-log__chips">
                          {!!log.details.ticket_id && (
                            <a
                              href={log.details.url as string}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="execution-log__link"
                            >
                              Open ticket →
                            </a>
                          )}
                          {!!log.details.ticket_type && (
                            <span className="execution-log__detail-chip">
                              {log.details.ticket_type as string}
                            </span>
                          )}
                          {!!log.details.epic_name && (
                            <span className="execution-log__detail-chip">
                              Epic: {log.details.epic_name as string}
                            </span>
                          )}
                          {!!log.details.classification && (
                            <span className="execution-log__detail-chip execution-log__detail-chip--classification">
                              LLM: {(log.details.classification as { ticket_type: string }).ticket_type} ({((log.details.classification as { confidence: number }).confidence * 100).toFixed(0)}%)
                            </span>
                          )}
                          {log.details.mock === true &&
                            log.details.kind !== 'calendar_invite' && (
                            <span className="execution-log__detail-chip execution-log__detail-chip--mock">
                              Mock Mode
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside className="action-item-detail__aside">
          <div className="orchestrator-panel">
            <div className="orchestrator-panel__header">
              <h3 className="orchestrator-panel__title">Orchestrator</h3>
              <button
                type="button"
                className="btn btn-primary btn--sm orchestrator-panel__retrigger"
                disabled={orchestratorBusy !== null}
                onClick={() => void handleRetriggerAll()}
              >
                {orchestratorBusy === 'retrigger' ? 'Running...' : 'Re-trigger All'}
              </button>
            </div>
            <div className="orchestrator-actions">
              <button
                type="button"
                className="orchestrator-btn"
                disabled={orchestratorBusy !== null}
                onClick={() => void handleTriggerAction('create_jira_ticket')}
              >
                <svg className="orchestrator-btn__icon" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm0 2v12h16V6H4zm2 2h12v2H6V8zm0 4h12v2H6v-2zm0 4h8v2H6v-2z"/>
                </svg>
                <span className="orchestrator-btn__text">
                  {orchestratorBusy === 'create_jira_ticket' ? 'Creating...' : 'Create Jira Issue'}
                </span>
                <span className="orchestrator-btn__arrow">→</span>
              </button>

              <button
                type="button"
                className="orchestrator-btn"
                disabled={orchestratorBusy !== null}
                onClick={() => void handleTriggerAction('update_confluence')}
              >
                <svg className="orchestrator-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
                <span className="orchestrator-btn__text">
                  {orchestratorBusy === 'update_confluence' ? 'Updating...' : 'Update Documentation'}
                </span>
                <span className="orchestrator-btn__arrow">→</span>
              </button>

              <button
                type="button"
                className="orchestrator-btn"
                disabled={orchestratorBusy !== null}
                onClick={() => void handleTriggerAction('create_subtask')}
              >
                <svg className="orchestrator-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M12 8v8m-4-4h8" />
                </svg>
                <span className="orchestrator-btn__text">
                  {orchestratorBusy === 'create_subtask' ? 'Creating...' : 'Create Subtask'}
                </span>
                <span className="orchestrator-btn__arrow">→</span>
              </button>
            </div>
          </div>

          <div className="orchestrator-panel orchestrator-panel--status">
            <h3 className="orchestrator-panel__title">Update Ticket Status</h3>
            <p className="orchestrator-panel__desc muted">
              Update the linked Jira issue status
            </p>
            <div className="orchestrator-actions orchestrator-actions--status">
              <button
                type="button"
                className="orchestrator-btn orchestrator-btn--status"
                disabled={orchestratorBusy !== null}
                onClick={() => void handleUpdateTicketStatus('In Progress')}
              >
                <svg className="orchestrator-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
                <span className="orchestrator-btn__text">
                  {orchestratorBusy === 'status_In Progress' ? 'Updating...' : 'Mark In Progress'}
                </span>
              </button>

              <button
                type="button"
                className="orchestrator-btn orchestrator-btn--status orchestrator-btn--done"
                disabled={orchestratorBusy !== null}
                onClick={() => void handleUpdateTicketStatus('Done')}
              >
                <svg className="orchestrator-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                <span className="orchestrator-btn__text">
                  {orchestratorBusy === 'status_Done' ? 'Updating...' : 'Mark Done'}
                </span>
              </button>
            </div>
          </div>

          <div className="orchestrator-panel orchestrator-panel--meeting">
            <h3 className="orchestrator-panel__title">Meeting MCP</h3>
            <p className="orchestrator-panel__desc muted">
              Push creates a Google Calendar event from this action item’s description and transcript
              snippet (times like “tomorrow 9am”); if none are found, it uses tomorrow at{' '}
              <strong>10:00</strong> in your API’s <code className="inline-code">APP_TIMEZONE</code>. Email
              uses SMTP from the API <code className="inline-code">.env</code>.
            </p>
            <div className="orchestrator-actions">
              <button
                type="button"
                className="orchestrator-btn"
                disabled={meetingMcpBusy}
                onClick={() => void handleMeetingMcp('calendar')}
              >
                <svg className="orchestrator-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
                <span className="orchestrator-btn__text">
                  {meetingMcpBusy ? 'Pushing...' : 'Push to Calendar'}
                </span>
                <span className="orchestrator-btn__arrow">→</span>
              </button>

              <button
                type="button"
                className="orchestrator-btn"
                disabled={meetingMcpBusy}
                onClick={() => void handleMeetingMcp('notify')}
              >
                <svg className="orchestrator-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                <span className="orchestrator-btn__text">
                  {meetingMcpBusy ? 'Notifying...' : 'Notify Participants'}
                </span>
                <span className="orchestrator-btn__arrow">→</span>
              </button>
            </div>
          </div>

          <div className="panel">
            <h3 className="panel__h">Item Details</h3>
            <div className="review-item__meta-grid">
              <div>
                <span className="meta-pair__k">Status</span>
                <span className="meta-pair__v">{statusLabel(item.status)}</span>
              </div>
              {item.status === 'approved' && item.approved_at ? (
                <div>
                  <span className="meta-pair__k">Approved at</span>
                  <span className="meta-pair__v">
                    <time dateTime={item.approved_at}>{formatPacific(item.approved_at)}</time> PT
                  </span>
                </div>
              ) : null}
              <div>
                <span className="meta-pair__k">Priority</span>
                <span className="meta-pair__v">{priorityLabel(item.priority)}</span>
              </div>
              <div>
                <span className="meta-pair__k">Confidence</span>
                <span className="meta-pair__v">{(item.confidence * 100).toFixed(0)}%</span>
              </div>
              <div>
                <span className="meta-pair__k">Created</span>
                <span className="meta-pair__v">
                  {item.created_at ? (
                    <>
                      <time dateTime={item.created_at}>{formatPacific(item.created_at)}</time> PT
                    </>
                  ) : (
                    '—'
                  )}
                </span>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
