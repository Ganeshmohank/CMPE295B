/** Fired after dashboard summary or review queue data changes so the nav badge can refetch. */
export const SUMMARY_STALE_EVENT = 'meeting-intelligence:summary-stale'

export function notifySummaryStale(): void {
  window.dispatchEvent(new CustomEvent(SUMMARY_STALE_EVENT))
}
