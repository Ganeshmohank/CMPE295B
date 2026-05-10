import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { InitialAvatar } from '../components/InitialAvatar'
import { api } from '../api'
import {
  invalidateMeetingDetailCache,
  invalidateProjectRosterCache,
  readMeetingDetailCache,
  readProjectRosterCache,
  writeMeetingDetailCache,
  writeProjectRosterCache,
} from '../lib/meetingDetailCache'
import { notifySummaryStale } from '../lib/summarySync'
import type {
  ActionItemStatus,
  MeetingDetailResponse,
  MeetingParticipantOut,
  NotionRecapOut,
  ProjectListItem,
  RelatedLinkOut,
} from '../types'

import { formatPacificDateTimeTz, fmtMs } from '../lib/format'

const SUGGESTION_CAP = 20
const RELATED_PAGE_SIZE = 10

function logStageLabel(stage: string): string {
  if (stage === 'notion_recap') return 'Notion recap'
  return stage.replace(/_/g, ' ')
}

function notionOpenUrl(recap: NotionRecapOut | null | undefined): string | null {
  if (!recap) return null
  const u = recap.url?.trim()
  if (u) return u
  const raw = recap.page_id
  if (!raw) return null
  const hex = String(raw).replace(/-/g, '')
  return hex.length === 32 ? `https://www.notion.so/${hex}` : null
}

function hasNotionRecapMeta(recap: NotionRecapOut | null | undefined): boolean {
  if (!recap) return false
  return Boolean(recap.posted_at || recap.page_id || (recap.url && recap.url.trim()))
}

// const PRIORITY_OPTIONS: Priority[] = ['critical', 'high', 'medium', 'low']

function actionStatusLabel(s: ActionItemStatus): string {
  if (s === 'pending_review') return 'Awaiting review'
  if (s === 'approved') return 'Approved'
  if (s === 'rejected') return 'Rejected'
  return 'Ticket created'
}

// function priorityClass(p: Priority): string {
//   if (p === 'critical') return 'prio prio--critical'
//   if (p === 'high') return 'prio prio--high'
//   if (p === 'medium') return 'prio prio--medium'
//   return 'prio prio--low'
// }

function relatedLinkHost(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return ''
  }
}

function RelatedContentPanel({
  links,
  placement,
  page,
  onPageChange,
}: {
  links: RelatedLinkOut[]
  /** Main column above logs (narrow viewports only). */
  placement: 'stack' | 'beside'
  page: number
  onPageChange: (p: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(links.length / RELATED_PAGE_SIZE))
  const slice = links.slice((page - 1) * RELATED_PAGE_SIZE, page * RELATED_PAGE_SIZE)

  const shell =
    placement === 'stack'
      ? `panel panel--elevated related-panel related-panel--stack${links.length === 0 ? ' panel--compact' : ''}`
      : 'rail-card related-panel related-panel--beside'

  return (
    <section
      className={shell}
      aria-label={placement === 'beside' ? 'Related links (beside context)' : 'Related links'}
    >
      <h3 className={placement === 'stack' ? 'panel__h' : 'rail-card__title'}>Related content</h3>
      <p className="rail-card__intro muted">
        External tools (dummy Atlassian-style URLs for now). Wire real OAuth / deep links when you connect
        Jira or Confluence.
      </p>
      {links.length === 0 ? (
        <p className="muted">No linked docs for this meeting.</p>
      ) : (
        <>
          <ul className="related-links">
            {slice.map((x, i) => {
              const host = relatedLinkHost(x.url)
              return (
                <li key={`${x.url}-${i}`}>
                  <a
                    href={x.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="related-links__a"
                  >
                    {x.title}
                  </a>
                  {host ? <span className="related-links__host muted">{host}</span> : null}
                </li>
              )
            })}
          </ul>
          {totalPages > 1 && (
            <nav className="pager pager--compact" aria-label="Related links pages">
              <button
                type="button"
                className="btn btn-ghost btn--sm"
                disabled={page <= 1}
                onClick={() => onPageChange(page - 1)}
              >
                Prev
              </button>
              <span className="pager__status muted">
                {page} / {totalPages}
              </span>
              <button
                type="button"
                className="btn btn-ghost btn--sm"
                disabled={page >= totalPages}
                onClick={() => onPageChange(page + 1)}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  )
}

function formatProjectsCatalogError(raw: string): string {
  let detail: string | undefined
  try {
    const j = JSON.parse(raw) as { detail?: unknown }
    if (typeof j.detail === 'string') detail = j.detail
  } catch {
    /* not JSON */
  }
  if (detail === 'Not Found') {
    return 'Not Found — restart the API server so it serves GET /api/projects/catalog (or pull latest backend and restart).'
  }
  return detail ?? raw
}

function isMeetingNotFoundError(raw: string): boolean {
  if (/Meeting not found/i.test(raw)) return true
  try {
    const j = JSON.parse(raw) as { detail?: unknown }
    const d = j.detail
    if (d === 'Meeting not found') return true
    if (typeof d === 'string' && d.includes('Meeting not found')) return true
  } catch {
    /* not JSON */
  }
  return false
}

export function MeetingDetailPage() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const [data, setData] = useState<MeetingDetailResponse | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [projectTheme, setProjectTheme] = useState('')
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [ctxDev, setCtxDev] = useState('')
  const [ctxPm, setCtxPm] = useState('')
  const [ctxBusy, setCtxBusy] = useState(false)
  const [ctxMsg, setCtxMsg] = useState<string | null>(null)
  const [projects, setProjects] = useState<ProjectListItem[]>([])
  const [projectsLoadErr, setProjectsLoadErr] = useState<string | null>(null)
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [themeOpen, setThemeOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const [relatedPage, setRelatedPage] = useState(1)
  const [projectRoster, setProjectRoster] = useState<MeetingParticipantOut[]>([])
  const [teamAddOpen, setTeamAddOpen] = useState(false)
  const [teamAddName, setTeamAddName] = useState('')
  const [teamAddEmail, setTeamAddEmail] = useState('')
  const [teamAddToProject, setTeamAddToProject] = useState(true)
  const [teamAddBusy, setTeamAddBusy] = useState(false)
  const [teamAddErr, setTeamAddErr] = useState<string | null>(null)
  const [actionBusy, setActionBusy] = useState<string | null>(null)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [bulkConfirmKind, setBulkConfirmKind] = useState<'approve' | 'reject' | null>(null)
  const [archiveConfirmKind, setArchiveConfirmKind] = useState<'archive' | 'restore' | null>(null)
  const [transcriptText, setTranscriptText] = useState('')
  const [transcriptOriginal, setTranscriptOriginal] = useState('')
  const [transcriptSaving, setTranscriptSaving] = useState(false)
  const [notionRecapBusy, setNotionRecapBusy] = useState(false)
  const [notionRecapMsg, setNotionRecapMsg] = useState<string | null>(null)
  const [notionBackgroundActive, setNotionBackgroundActive] = useState(false)
  const [postApproveJobsWarmup, setPostApproveJobsWarmup] = useState(false)
  const [reExtractBusy, setReExtractBusy] = useState(false)
  const [archiveBusy, setArchiveBusy] = useState(false)
  const notionPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const approveWarmupTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** When trace says recap succeeded but meeting payload has no recap meta (stale cache), poll once per meeting id. */
  const notionMismatchAutoPollRef = useRef<string | null>(null)
  const comboboxRef = useRef<HTMLDivElement>(null)

  const pendingActionCount = useMemo(() => {
    if (!data) return 0
    return data.action_items.filter((a) => a.status === 'pending_review').length
  }, [data])

  const transcriptRows = useMemo(() => {
    const text = transcriptText.trim()
    if (!text) return 2

    const hardLines = text.split(/\r\n|\r|\n/).length
    const softLines = Math.ceil(text.length / 95)
    return Math.min(7, Math.max(4, hardLines + softLines))
  }, [transcriptText])

  const notionRecapLogs = useMemo(() => {
    if (!data) return []
    return [...data.processing_logs]
      .filter((l) => l.stage === 'notion_recap')
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
  }, [data])

  const stopNotionRecapPoll = useCallback(() => {
    if (notionPollRef.current != null) {
      clearInterval(notionPollRef.current)
      notionPollRef.current = null
    }
    setNotionBackgroundActive(false)
  }, [])

  const startNotionRecapPoll = useCallback(
    (meetingId: string) => {
      stopNotionRecapPoll()
      setNotionBackgroundActive(true)
      let attempts = 0
      const maxAttempts = 40
      const tick = async () => {
        attempts += 1
        invalidateMeetingDetailCache(meetingId)
        try {
          const d = await api.meetingDetail(meetingId)
          writeMeetingDetailCache(meetingId, d)
          setData(d)
          const r = d.meeting.notion_recap
          const ready = Boolean(r?.page_id || r?.posted_at || (r?.url && r.url.trim()))
          if (ready || attempts >= maxAttempts) {
            stopNotionRecapPoll()
          }
        } catch {
          if (attempts >= maxAttempts) stopNotionRecapPoll()
        }
      }
      void tick()
      notionPollRef.current = setInterval(() => void tick(), 1700)
    },
    [stopNotionRecapPoll],
  )

  useEffect(() => {
    return () => {
      stopNotionRecapPoll()
      if (approveWarmupTimerRef.current != null) {
        clearTimeout(approveWarmupTimerRef.current)
        approveWarmupTimerRef.current = null
      }
      setPostApproveJobsWarmup(false)
    }
  }, [id, stopNotionRecapPoll])

  useEffect(() => {
    notionMismatchAutoPollRef.current = null
  }, [id])

  useEffect(() => {
    if (!id || !data) return
    const logOk = notionRecapLogs.some((l) => l.status === 'success')
    const hasMeta = hasNotionRecapMeta(data.meeting.notion_recap)
    if (hasMeta) {
      if (notionMismatchAutoPollRef.current === id) notionMismatchAutoPollRef.current = null
      return
    }
    if (!logOk) return
    if (notionMismatchAutoPollRef.current === id) return
    notionMismatchAutoPollRef.current = id
    startNotionRecapPoll(id)
  }, [id, data, notionRecapLogs, startNotionRecapPoll])

  useEffect(() => {
    if (!data) return
    const h = location.hash
    if (h !== '#action-review' && !h.startsWith('#action-item-')) return
    requestAnimationFrame(() => {
      document.querySelector(h)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }, [data, location.hash])

  useEffect(() => {
    if (!id) return
    let alive = true
    setErr(null)

    const initializeEditableFields = (d: MeetingDetailResponse) => {
      const rawText = d.transcript?.raw_text ?? ''
      setTranscriptText(rawText)
      setTranscriptOriginal(rawText)
    }

    const cached = readMeetingDetailCache(id)
    if (cached) {
      setData(cached)
      setProjectTheme(cached.meeting.project_theme ?? '')
      setSelectedProjectId(cached.meeting.project_id ?? null)
      setCtxDev(cached.meeting.context_developer ?? '')
      setCtxPm(cached.meeting.context_pm ?? '')
      initializeEditableFields(cached)
      return () => {
        alive = false
      }
    }

    setSelectedProjectId(null)
    setProjectRoster([])
    setData(null)
    api
      .meetingDetail(id)
      .then((d) => {
        if (!alive) return
        writeMeetingDetailCache(id, d)
        setData(d)
        setProjectTheme(d.meeting.project_theme ?? '')
        setSelectedProjectId(d.meeting.project_id ?? null)
        setCtxDev(d.meeting.context_developer ?? '')
        setCtxPm(d.meeting.context_pm ?? '')
        initializeEditableFields(d)
      })
      .catch((e: Error) => {
        if (alive) {
          setErr(e.message)
          setData(null)
          if (isMeetingNotFoundError(e.message)) invalidateMeetingDetailCache(id)
        }
      })
    return () => {
      alive = false
    }
  }, [id])

  useEffect(() => {
    setRelatedPage(1)
  }, [id])

  /** Load initiative roster whenever the selected catalog project changes (including after meeting load). */
  useEffect(() => {
    if (!selectedProjectId) {
      setProjectRoster([])
      return
    }
    let alive = true
    const rosterCached = readProjectRosterCache(selectedProjectId)
    if (rosterCached) {
      setProjectRoster(rosterCached)
      return () => {
        alive = false
      }
    }
    api
      .projectTeamMembers(selectedProjectId)
      .then((rows) => {
        if (!alive) return
        writeProjectRosterCache(selectedProjectId, rows)
        setProjectRoster(rows)
      })
      .catch(() => {
        if (alive) setProjectRoster([])
      })
    return () => {
      alive = false
    }
  }, [selectedProjectId])

  useEffect(() => {
    let alive = true
    setProjectsLoadErr(null)
    setProjectsLoading(true)
    api
      .projectsList()
      .then((list) => {
        if (alive) {
          setProjects(list)
          setProjectsLoadErr(null)
        }
      })
      .catch((e: Error) => {
        if (alive) {
          setProjects([])
          setProjectsLoadErr(
            formatProjectsCatalogError(e.message || 'Could not load project catalog'),
          )
        }
      })
      .finally(() => {
        if (alive) setProjectsLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    function onDocDown(e: MouseEvent) {
      if (!comboboxRef.current?.contains(e.target as Node)) {
        setThemeOpen(false)
        setActiveIdx(-1)
      }
    }
    document.addEventListener('mousedown', onDocDown)
    return () => document.removeEventListener('mousedown', onDocDown)
  }, [])

  const displayTeam = useMemo(() => {
    const meetingList = data?.participants ?? []
    const seen = new Set<string>()
    const out: MeetingParticipantOut[] = []
    for (const x of meetingList) {
      seen.add(x.participant.id)
      out.push(x)
    }
    for (const x of projectRoster) {
      if (!seen.has(x.participant.id)) {
        seen.add(x.participant.id)
        out.push(x)
      }
    }
    return out
  }, [data?.participants, projectRoster])

  async function submitTeamAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!id || !teamAddName.trim()) return
    setTeamAddBusy(true)
    setTeamAddErr(null)
    try {
      await api.addMeetingTeamMember(id, {
        display_name: teamAddName.trim(),
        email: teamAddEmail.trim() === '' ? null : teamAddEmail.trim(),
        add_to_linked_project: teamAddToProject,
      })
      const d = await api.meetingDetail(id)
      writeMeetingDetailCache(id, d)
      setData(d)
      if (selectedProjectId) {
        invalidateProjectRosterCache(selectedProjectId)
        try {
          const rows = await api.projectTeamMembers(selectedProjectId)
          writeProjectRosterCache(selectedProjectId, rows)
          setProjectRoster(rows)
        } catch {
          setProjectRoster([])
        }
      }
      setTeamAddName('')
      setTeamAddEmail('')
      setTeamAddOpen(false)
    } catch (err) {
      setTeamAddErr(err instanceof Error ? err.message : String(err))
    } finally {
      setTeamAddBusy(false)
    }
  }

  /** Filtered rows; if the meeting label does not match any catalog name, still show catalog (was hiding the whole dropdown). */
  const themeSuggestions = useMemo(() => {
    const q = projectTheme.trim().toLowerCase()
    const base = projects
    const filtered = q
      ? base.filter((p) => p.name.toLowerCase().includes(q))
      : base
    const capped = filtered.slice(0, SUGGESTION_CAP)
    if (capped.length > 0) {
      return { rows: capped, note: null as string | null }
    }
    if (base.length === 0) {
      return { rows: [] as ProjectListItem[], note: null as string | null }
    }
    return {
      rows: base.slice(0, SUGGESTION_CAP),
      note: 'No catalog name contains your text — pick one below or keep typing a custom label.',
    }
  }, [projectTheme, projects])

  async function saveContext() {
    if (!id) return
    setCtxBusy(true)
    setCtxMsg(null)
    try {
      const m = await api.patchMeetingContext(id, {
        project_id: selectedProjectId,
        project_theme: projectTheme.trim() || null,
        context_developer: ctxDev.trim() === '' ? null : ctxDev.trim(),
        context_pm: ctxPm.trim() === '' ? null : ctxPm.trim(),
      })
      setProjectTheme(m.project_theme ?? '')
      setSelectedProjectId(m.project_id ?? null)
      invalidateProjectRosterCache()
      invalidateMeetingDetailCache(id)
      const d = await api.meetingDetail(id)
      writeMeetingDetailCache(id, d)
      setData(d)
      setRelatedPage(1)
      try {
        const fresh = await api.projectsList()
        setProjects(fresh)
        setProjectsLoadErr(null)
      } catch {
        /* keep catalog as-is */
      }
      setCtxMsg('Saved.')
    } catch (e) {
      setCtxMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setCtxBusy(false)
    }
  }

  function pickTheme(p: ProjectListItem) {
    setProjectTheme(p.name)
    setSelectedProjectId(p.id?.trim() ? p.id : null)
    setThemeOpen(false)
    setActiveIdx(-1)
  }

  function onThemeKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!themeOpen && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      setThemeOpen(true)
      setActiveIdx(themeSuggestions.rows.length > 0 ? 0 : -1)
      e.preventDefault()
      return
    }
    if (!themeOpen) return
    if (e.key === 'Escape') {
      setThemeOpen(false)
      setActiveIdx(-1)
      e.preventDefault()
      return
    }
    const n = themeSuggestions.rows.length
    if (e.key === 'ArrowDown') {
      setActiveIdx((i) => (n === 0 ? -1 : Math.min(i < 0 ? 0 : i + 1, n - 1)))
      e.preventDefault()
      return
    }
    if (e.key === 'ArrowUp') {
      setActiveIdx((i) => (n === 0 ? -1 : Math.max((i < 0 ? n : i) - 1, 0)))
      e.preventDefault()
      return
    }
    if (e.key === 'Enter' && activeIdx >= 0 && themeSuggestions.rows[activeIdx]) {
      pickTheme(themeSuggestions.rows[activeIdx]!)
      e.preventDefault()
    }
  }

  async function saveTranscript() {
    if (!id || transcriptText === transcriptOriginal) return
    setTranscriptSaving(true)
    try {
      await api.patchTranscript(id, { raw_text: transcriptText })
      setTranscriptOriginal(transcriptText)
      notifySummaryStale()
      invalidateMeetingDetailCache(id)
    } catch (e) {
      console.error('Failed to save transcript:', e)
    } finally {
      setTranscriptSaving(false)
    }
  }

  async function bulkApprovePendingActionsImpl() {
    if (!id) return
    setActionBusy('bulk-a')
    setActionMsg(null)
    try {
      const { updated } = await api.bulkApproveMeeting(id)
      notifySummaryStale()
      invalidateMeetingDetailCache(id)
      const d = await api.meetingDetail(id)
      writeMeetingDetailCache(id, d)
      setData(d)
      if (updated > 0) {
        setPostApproveJobsWarmup(true)
        if (approveWarmupTimerRef.current != null) clearTimeout(approveWarmupTimerRef.current)
        approveWarmupTimerRef.current = setTimeout(() => {
          setPostApproveJobsWarmup(false)
          approveWarmupTimerRef.current = null
        }, 26000)
        startNotionRecapPoll(id)
      }
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setActionBusy(null)
    }
  }

  async function bulkRejectPendingActionsImpl() {
    if (!id) return
    setActionBusy('bulk-r')
    setActionMsg(null)
    try {
      await api.bulkRejectMeeting(id)
      notifySummaryStale()
      invalidateMeetingDetailCache(id)
      const d = await api.meetingDetail(id)
      writeMeetingDetailCache(id, d)
      setData(d)
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setActionBusy(null)
    }
  }

  async function postNotionRecapNow(force: boolean) {
    if (!id) return
    setNotionRecapBusy(true)
    setNotionRecapMsg(null)
    try {
      const r = await api.postNotionMeetingRecap(id, { force })
      if (r.posted) {
        setNotionRecapMsg(r.mock ? 'Recap posted to Notion (mock).' : 'Recap posted to Notion.')
      } else {
        const hint = [r.skipped_reason, r.notion_url].filter(Boolean).join(' · ')
        setNotionRecapMsg(hint || 'Recap was not posted.')
      }
      invalidateMeetingDetailCache(id)
      const d = await api.meetingDetail(id)
      writeMeetingDetailCache(id, d)
      setData(d)
      if (r.posted || r.skipped_reason === 'already_posted') {
        startNotionRecapPoll(id)
      }
    } catch (e) {
      setNotionRecapMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setNotionRecapBusy(false)
    }
  }

  async function reExtractActionsImpl() {
    if (!id) return
    const raw = transcriptText.trim()
    if (!raw) {
      setActionMsg('Add or save a transcript first, then re-run extraction.')
      return
    }
    setReExtractBusy(true)
    setActionMsg(null)
    try {
      const r = await api.postReExtractActions(id)
      setActionMsg(
        `Re-extracted ${r.extracted_count} action item(s) (${fmtMs(r.processing_time_ms)}). All previous items for this meeting were replaced.`,
      )
      notifySummaryStale()
      invalidateMeetingDetailCache(id)
      const d = await api.meetingDetail(id)
      writeMeetingDetailCache(id, d)
      setData(d)
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setReExtractBusy(false)
    }
  }

  async function applyMeetingArchiveChange(next: boolean) {
    if (!id) return
    setArchiveBusy(true)
    setActionMsg(null)
    try {
      await api.patchMeetingArchive(id, next)
      notifySummaryStale()
      invalidateMeetingDetailCache(id)
      const d = await api.meetingDetail(id)
      writeMeetingDetailCache(id, d)
      setData(d)
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setArchiveBusy(false)
    }
  }

  if (!id) return <p className="muted">Missing meeting id.</p>
  if (err && isMeetingNotFoundError(err)) {
    return (
      <div className="meeting-missing">
        <p className="detail-back">
          <Link to="/meetings">← Back to meetings</Link>
        </p>
        <div className="error-banner meeting-missing__banner" role="alert">
          <strong>Meeting not found.</strong> The id in your URL is not in the database—common after
          re-running the seed script, which generates new ids. Open the meetings list and pick a current
          row.
        </div>
        <p className="muted meeting-missing__hint">
          <Link to="/meetings">Browse all meetings</Link>
        </p>
      </div>
    )
  }
  if (err) return <div className="error-banner">{err}</div>
  if (!data) return <p className="muted">Loading meeting…</p>

  const { meeting, transcript, action_items, processing_logs } = data
  const relatedLinks = data.related_links ?? []
  const teamSectionTitle = projectTheme.trim() ? `Team · ${projectTheme.trim()}` : 'Team'
  const notionRecapUrl = notionOpenUrl(meeting.notion_recap)
  const notionHasMeta = hasNotionRecapMeta(meeting.notion_recap)
  const notionLogOk = notionRecapLogs.some((l) => l.status === 'success')
  const showNotionLive =
    notionRecapBusy || notionBackgroundActive || postApproveJobsWarmup

  return (
    <>
      <ConfirmDialog
        open={bulkConfirmKind !== null}
        title={
          bulkConfirmKind === 'reject'
            ? 'Reject all pending items?'
            : 'Approve all pending items?'
        }
        message={
          bulkConfirmKind === 'reject'
            ? 'Every action item still awaiting review for this meeting will be marked rejected.'
            : 'Every action item still awaiting review for this meeting will be marked approved.'
        }
        confirmLabel={bulkConfirmKind === 'reject' ? 'Reject all' : 'Approve all'}
        cancelLabel="Cancel"
        variant={bulkConfirmKind === 'reject' ? 'danger' : 'default'}
        onCancel={() => setBulkConfirmKind(null)}
        onConfirm={() => {
          const kind = bulkConfirmKind
          setBulkConfirmKind(null)
          if (kind === 'approve') void bulkApprovePendingActionsImpl()
          else if (kind === 'reject') void bulkRejectPendingActionsImpl()
        }}
      />
      <ConfirmDialog
        open={archiveConfirmKind !== null}
        title={
          archiveConfirmKind === 'archive'
            ? 'Archive this meeting?'
            : 'Restore this meeting?'
        }
        message={
          archiveConfirmKind === 'archive'
            ? 'It will disappear from the main Meetings list but stay available under Archived meetings.'
            : 'It will show again on the main Meetings list.'
        }
        confirmLabel={
          archiveConfirmKind === 'archive' ? 'Archive meeting' : 'Restore to meetings'
        }
        cancelLabel="Cancel"
        variant={archiveConfirmKind === 'archive' ? 'danger' : 'default'}
        onCancel={() => setArchiveConfirmKind(null)}
        onConfirm={() => {
          const kind = archiveConfirmKind
          setArchiveConfirmKind(null)
          if (kind === 'archive') void applyMeetingArchiveChange(true)
          else if (kind === 'restore') void applyMeetingArchiveChange(false)
        }}
      />
      <p className="detail-back">
        <Link to={meeting.archived ? '/archived-meetings' : '/meetings'}>
          ← Back to {meeting.archived ? 'archived meetings' : 'meetings'}
        </Link>
      </p>

      <div className="detail-page detail-page--meeting">
        <header className="detail-page__head">
          <h1 className="detail-title">{meeting.title}</h1>
          <p className="detail-lede muted">
            {formatPacificDateTimeTz(meeting.start_time)} ·{' '}
            {(meeting.duration_minutes ?? 0) > 0 ? `${meeting.duration_minutes} min` : 'Duration —'} ·{' '}
            {meeting.participants_count} people · {meeting.source} · {meeting.status} ·{' '}
            {meeting.processing_status}
            {' · '}
            <span title="America/Los_Angeles">Pacific time</span>
          </p>
          {meeting.archived ? (
            <p className="detail-archived-banner muted" role="status">
              This meeting is <strong>archived</strong> (hidden from the main list).
            </p>
          ) : null}
          <div className="detail-meeting-toolbar btn-row">
            <button
              type="button"
              className="btn btn-ghost btn--sm"
              disabled={reExtractBusy || archiveBusy || !transcript}
              onClick={() => void reExtractActionsImpl()}
              title={
                transcript
                  ? 'Replaces every action item for this meeting. Uses the saved transcript plus meeting context (initiative + engineering/PM fields). OpenAI skips vague or unclear tasks. Save the transcript first if you edited it without saving.'
                  : 'No transcript on file'
              }
            >
              {reExtractBusy ? 'Re-extracting…' : 'Re-extract action items'}
            </button>
            {meeting.archived ? (
              <button
                type="button"
                className="btn btn-primary btn--sm"
                disabled={archiveBusy || reExtractBusy || archiveConfirmKind !== null}
                onClick={() => setArchiveConfirmKind('restore')}
              >
                {archiveBusy ? 'Updating…' : 'Restore to meetings'}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-ghost btn--sm btn--danger-outline"
                disabled={archiveBusy || reExtractBusy || archiveConfirmKind !== null}
                onClick={() => setArchiveConfirmKind('archive')}
              >
                {archiveBusy ? 'Updating…' : 'Archive meeting'}
              </button>
            )}
          </div>
        </header>

        <div className="detail-page__split">
        <div className="detail-page__primary">
        <section
          className={`detail-block detail-block--transcript panel panel--elevated${transcript ? '' : ' panel--compact'}`}
        >
          <div className="panel__h-row">
            <h3 className="panel__h">Transcript</h3>
            {transcript && transcriptText !== transcriptOriginal && (
              <button
                type="button"
                className="inline-save-btn"
                disabled={transcriptSaving}
                onClick={() => void saveTranscript()}
                title="Save transcript"
                aria-label="Save transcript"
              >
                {transcriptSaving ? (
                  <span className="inline-save-spinner" />
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                    <polyline points="17 21 17 13 7 13 7 21" />
                    <polyline points="7 3 7 8 15 8" />
                  </svg>
                )}
              </button>
            )}
          </div>
          {transcript ? (
            <textarea
              className="transcript-box transcript-box--editable"
              rows={transcriptRows}
              value={transcriptText}
              onChange={(e) => setTranscriptText(e.target.value)}
            />
          ) : (
            <p className="muted">No transcript.</p>
          )}
        </section>

        <section
          className="detail-block detail-block--notion panel panel--elevated"
          aria-label="Notion meeting recap"
        >
          <div className="panel__h-row panel__h-row--notion">
            <h3 className="panel__h">Notion recap</h3>
            {showNotionLive ? (
              <span className="notion-live-indicator" title="Notion recap or orchestration in progress">
                <span className="notion-live-indicator__dot" aria-hidden />
                <span className="notion-live-indicator__label">Working…</span>
              </span>
            ) : null}
          </div>
          <p className="rail-card__intro muted">
            Recap posts after ingest, when you <strong>approve items</strong> (runs in the background), or when
            you use the button. Approvals also trigger Jira, Confluence, and calendar when live.
          </p>
          {notionRecapUrl || notionHasMeta ? (
            <p className="muted">
              {meeting.notion_recap?.posted_at ? (
                <>
                  Last posted{' '}
                  <time dateTime={meeting.notion_recap.posted_at}>
                    {formatPacificDateTimeTz(meeting.notion_recap.posted_at)}
                  </time>{' '}
                  {notionRecapUrl ? (
                    <>
                      {' '}
                      ·{' '}
                      <a href={notionRecapUrl} target="_blank" rel="noopener noreferrer">
                        Open in Notion
                      </a>
                    </>
                  ) : null}
                </>
              ) : notionRecapUrl ? (
                <>
                  <a href={notionRecapUrl} target="_blank" rel="noopener noreferrer">
                    Open recap in Notion
                  </a>
                </>
              ) : (
                <>Recap on file — link syncing…</>
              )}
            </p>
          ) : notionLogOk && showNotionLive ? (
            <p className="muted">Recap posted — fetching page link…</p>
          ) : notionLogOk ? (
            <p className="muted">
              Recap logged.{' '}
              <button type="button" className="btn btn-ghost btn--sm" onClick={() => void startNotionRecapPoll(id!)}>
                Refresh link
              </button>
            </p>
          ) : (
            <p className="muted">No Notion recap posted for this meeting yet.</p>
          )}
          {notionRecapMsg ? <p className="actions-panel-msg muted">{notionRecapMsg}</p> : null}
          <div className="notion-recap-toolbar">
            <button
              type="button"
              className="btn btn-primary btn--sm"
              disabled={notionRecapBusy || !id}
              onClick={() => void postNotionRecapNow(false)}
            >
              {notionRecapBusy ? 'Posting…' : 'Post recap to Notion'}
            </button>
            {notionRecapUrl ? (
              <button
                type="button"
                className="btn btn-ghost btn--sm"
                disabled={notionRecapBusy}
                onClick={() => {
                  if (
                    window.confirm(
                      'Create a new Notion recap page even if one already exists? The old page is not deleted.',
                    )
                  ) {
                    void postNotionRecapNow(true)
                  }
                }}
              >
                Post again (new page)
              </button>
            ) : null}
          </div>
          {notionRecapLogs.length > 0 ? (
            <div className="notion-recap-trace">
              <p className="notion-recap-trace__title">Activity trace</p>
              <ol>
                {notionRecapLogs.map((l) => (
                  <li key={l.id}>
                    <strong>{formatPacificDateTimeTz(l.timestamp)}</strong> — {l.status}: {l.message}
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </section>

        <section
          id="action-review"
          className={`detail-block detail-block--actions panel panel--elevated${action_items.length === 0 ? ' panel--compact' : ''}`}
          aria-label="Extracted action items"
        >
          <div className="actions-panel-head">
            <h3 className="panel__h">Extracted action items</h3>
            <div className="actions-panel-head__actions">
              <button
                type="button"
                className="btn btn-ghost btn--sm"
                disabled={reExtractBusy || archiveBusy || !transcript || actionBusy !== null}
                onClick={() => void reExtractActionsImpl()}
                title={
                  transcript
                    ? 'Same as toolbar: replaces all items from saved transcript + meeting context; vague tasks omitted. Save transcript if needed.'
                    : 'No transcript on file'
                }
              >
                {reExtractBusy ? 'Re-extracting…' : 'Re-extract'}
              </button>
              {id && pendingActionCount > 0 && (
                <Link
                  className="btn btn-ghost btn--sm actions-panel-head__link"
                  to={`/review?meeting=${encodeURIComponent(id)}`}
                >
                  Open review queue ({pendingActionCount} awaiting)
                </Link>
              )}
            </div>
          </div>
          {actionMsg && <p className="actions-panel-msg muted">{actionMsg}</p>}
          {action_items.length === 0 ? (
            <p className="muted">No action items extracted.</p>
          ) : (
            <>
              {pendingActionCount > 0 && (
                <div className="action-items-bulk-toolbar">
                  <button
                    type="button"
                    className="btn btn-primary btn--sm"
                    disabled={actionBusy !== null}
                    onClick={() => setBulkConfirmKind('approve')}
                  >
                    Approve all pending
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn--sm btn--danger-outline"
                    disabled={actionBusy !== null}
                    onClick={() => setBulkConfirmKind('reject')}
                  >
                    Reject all pending
                  </button>
                </div>
              )}
              <ul className="detail-action-list detail-action-list--cards detail-action-list--compact">
                {action_items.map((a) => (
                  <li key={a.id} id={`action-item-${a.id}`} className="detail-action-li detail-action-li--compact">
                    <div className="detail-action-li__head">
                      <div className="detail-action-li__badges">
                        <span
                          className={
                            a.status === 'pending_review'
                              ? 'action-item-status action-item-status--pending'
                              : a.status === 'approved'
                                ? 'action-item-status action-item-status--ok'
                                : 'action-item-status action-item-status--muted'
                          }
                        >
                          {actionStatusLabel(a.status)}
                        </span>
                        {a.status === 'pending_review' && id && (
                          <Link
                            className="action-item-queue-link"
                            to={`/review?meeting=${encodeURIComponent(id)}`}
                          >
                            In review queue →
                          </Link>
                        )}
                      </div>
                      <span className="detail-action-li__model muted">
                        model {(a.confidence * 100).toFixed(0)}%
                      </span>
                      <Link
                        to={`/action-items/${a.id}`}
                        className="action-item-edit-icon"
                        title="Edit & orchestrate"
                        aria-label="Edit action item"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                          <path d="m15 5 4 4" />
                        </svg>
                      </Link>
                    </div>
                    <Link to={`/action-items/${a.id}`} className="detail-action-desc-link">
                      <p className="detail-action-desc detail-action-desc--compact">{a.description}</p>
                    </Link>
                    {a.source_snippet && (
                      <p className="detail-action-snippet muted" title={a.source_snippet}>
                        {a.source_snippet}
                      </p>
                    )}
                    {a.status === 'approved' && a.approved_at ? (
                      <p className="detail-action-approved-at muted">
                        Approved{' '}
                        <time dateTime={a.approved_at}>{formatPacificDateTimeTz(a.approved_at)}</time>
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <div className="detail-block detail-block--related-wrap" aria-label="Related links">
          <RelatedContentPanel
            links={relatedLinks}
            placement="stack"
            page={relatedPage}
            onPageChange={setRelatedPage}
          />
          <RelatedContentPanel
            links={relatedLinks}
            placement="beside"
            page={relatedPage}
            onPageChange={setRelatedPage}
          />
        </div>

        <section className="detail-block detail-block--logs panel panel--elevated">
          <h3 className="panel__h">Processing logs</h3>
          <div className="table-wrap table-wrap--plain">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Stage</th>
                  <th>Status</th>
                  <th>Message</th>
                  <th>Ms</th>
                </tr>
              </thead>
              <tbody>
                {processing_logs.map((l) => (
                  <tr key={l.id}>
                    <td>{formatPacificDateTimeTz(l.timestamp)}</td>
                    <td>{logStageLabel(l.stage)}</td>
                    <td>{l.status}</td>
                    <td>{l.message}</td>
                    <td>{l.processing_time_ms ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        </div>

        <div className="detail-page__rail" aria-label="Team and meeting context">
        <aside className="detail-block detail-block--participants rail-card">
          <h3 className="rail-card__title rail-card__title--team">{teamSectionTitle}</h3>
          <p className="muted team-roster-hint">
            Avatars are everyone in this meeting; choosing a catalog project below also merges that
            initiative’s roster so the list updates when you switch projects.
          </p>
          <div className="team-toolbar">
            <ul className="avatar-stack avatar-stack--with-tip" aria-label={`People on ${teamSectionTitle}`}>
              {displayTeam.map((p) => (
                <li
                  key={p.participant.id}
                  className="avatar-stack__item avatar-stack__item--fast-tip"
                  aria-label={p.participant.display_name}
                  data-tooltip={p.participant.display_name}
                  tabIndex={0}
                >
                  <InitialAvatar name={p.participant.display_name} />
                </li>
              ))}
            </ul>
            <button
              type="button"
              className="btn btn-ghost team-add-btn"
              aria-expanded={teamAddOpen}
              aria-label="Add team member"
              title="Add team member"
              onClick={() => {
                setTeamAddOpen((o) => !o)
                setTeamAddErr(null)
              }}
            >
              +
            </button>
          </div>
          {teamAddOpen ? (
            <form className="team-add-form" onSubmit={(ev) => void submitTeamAdd(ev)}>
              <label className="field-label" htmlFor="team-add-name">
                Name
              </label>
              <input
                id="team-add-name"
                className="field-input"
                value={teamAddName}
                onChange={(e) => setTeamAddName(e.target.value)}
                placeholder="Full name"
                autoComplete="name"
                required
              />
              <label className="field-label" htmlFor="team-add-email">
                Email <span className="muted">(optional)</span>
              </label>
              <input
                id="team-add-email"
                className="field-input"
                type="email"
                value={teamAddEmail}
                onChange={(e) => setTeamAddEmail(e.target.value)}
                placeholder="name@company.com"
                autoComplete="email"
              />
              <label className="field-label field-label--inline">
                <input
                  type="checkbox"
                  checked={teamAddToProject}
                  onChange={(e) => setTeamAddToProject(e.target.checked)}
                />{' '}
                Also add to linked project roster (uses saved project on this meeting)
              </label>
              {teamAddErr ? (
                <p className="team-add-err muted" role="alert">
                  {teamAddErr}
                </p>
              ) : null}
              <button type="submit" className="btn btn-primary btn--sm" disabled={teamAddBusy}>
                {teamAddBusy ? 'Adding…' : 'Add to meeting'}
              </button>
            </form>
          ) : null}
        </aside>

        <div className="detail-block detail-block--context" aria-label="Meeting context">
          <div className="rail-card rail-card--context">
            <h3 className="rail-card__title">Context for your team</h3>
            <p className="rail-card__intro muted">
              Initiatives live in the <code className="inline-code">projects</code> collection (shared
              context). This meeting links via <code className="inline-code">project_id</code>; typing a
              custom label clears the link. Next-step fields can override the project template for this
              meeting only (leave blank to inherit).
            </p>
            <div
              className={`combobox${themeOpen ? ' combobox--open' : ''}`}
              ref={comboboxRef}
            >
              <label className="field-label" htmlFor="project-theme-input">
                Project / initiative
              </label>
              <div className="combobox__row">
                <input
                  id="project-theme-input"
                  className="field-input combobox__input"
                  autoComplete="off"
                  role="combobox"
                  aria-expanded={themeOpen}
                  aria-controls="project-theme-listbox"
                  aria-autocomplete="list"
                  value={projectTheme}
                  onChange={(e) => {
                    setProjectTheme(e.target.value)
                    setSelectedProjectId(null)
                    setThemeOpen(true)
                    setActiveIdx(-1)
                  }}
                  onFocus={() => {
                    setThemeOpen(true)
                    setActiveIdx(-1)
                  }}
                  onKeyDown={onThemeKeyDown}
                  placeholder="e.g. Checkout reliability program — type to filter"
                />
                <button
                  type="button"
                  className="combobox__toggle"
                  aria-label={themeOpen ? 'Close project list' : 'Open project list'}
                  aria-expanded={themeOpen}
                  tabIndex={-1}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    setThemeOpen((o) => !o)
                    setActiveIdx(-1)
                  }}
                >
                  {themeOpen ? '▲' : '▼'}
                </button>
              </div>
              {themeOpen && !projectsLoading && themeSuggestions.rows.length > 0 && (
                <div className="combobox__popover">
                  {themeSuggestions.note && (
                    <p className="combobox__list-note muted" role="status">
                      {themeSuggestions.note}
                    </p>
                  )}
                  <ul
                    id="project-theme-listbox"
                    className="combobox__list"
                    role="listbox"
                    aria-label="Existing project or initiative names"
                  >
                    {themeSuggestions.rows.map((p, i) => (
                      <li key={p.id || `theme:${p.name}`} role="presentation">
                        <button
                          type="button"
                          role="option"
                          aria-selected={i === activeIdx}
                          className={`combobox__opt${i === activeIdx ? ' combobox__opt--active' : ''}`}
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => pickTheme(p)}
                        >
                          {p.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {themeOpen && !projectsLoading && projects.length === 0 && !projectsLoadErr && (
                <div className="combobox__popover combobox__popover--empty" role="status">
                  <p className="combobox__empty-msg muted">
                    No initiatives in the catalog yet. Type a custom name or run seed to add projects.
                  </p>
                </div>
              )}
              {projectsLoadErr && (
                <p className="combobox__hint combobox__hint--err muted" role="status">
                  Project catalog unavailable ({projectsLoadErr}). You can still type a custom initiative
                  name.
                </p>
              )}
            </div>
            <label className="field-label">
              Next steps — engineering / IC
              <textarea
                className="field-input field-input--area field-input--scrollable"
                rows={5}
                value={ctxDev}
                onChange={(e) => setCtxDev(e.target.value)}
                placeholder="Leave empty to inherit from project; or add meeting-specific overrides…"
              />
            </label>
            <label className="field-label">
              Next steps — PM / stakeholders
              <textarea
                className="field-input field-input--area field-input--scrollable"
                rows={5}
                value={ctxPm}
                onChange={(e) => setCtxPm(e.target.value)}
                placeholder="Leave empty to inherit from project; or add PM / stakeholder notes…"
              />
            </label>
            {ctxMsg && <p className="rail-card__msg muted">{ctxMsg}</p>}
            <button
              type="button"
              className="btn btn-primary rail-card__save"
              disabled={ctxBusy}
              onClick={() => void saveContext()}
            >
              {ctxBusy ? 'Saving…' : 'Save context'}
            </button>
          </div>
        </div>
        </div>
        </div>
      </div>
    </>
  )
}
