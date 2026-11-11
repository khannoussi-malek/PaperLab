import { ApiError, api, type DraftReview, type DraftReviewEstimate } from '@/api/client'

export type DraftMode = 'light' | 'full'
export type DraftEstimate = DraftReviewEstimate['modes'][number]
export type DraftStart = Parameters<typeof api.startDraftReview>[1]
type Severity = DraftReview['issues'][number]['severity']

const REASON: Record<string, string> = {
  paper_too_short: 'There is not enough text to review yet.',
  paper_too_long: 'The draft is too long to review at once.',
  model_unavailable: 'The model could not be reached.',
  model_error: "The model's answer could not be used. Try again.",
  cancelled: 'Cancelled.',
  queue_unavailable: 'The worker is not running.',
}
const UNKNOWN_REASON = 'The review failed. Try again.'

/** A failed review's reason in plain words; an unknown code is not blamed on the model. */
export const reasonText = (reason: string | null): string => (reason && Object.hasOwn(REASON, reason) ? REASON[reason] : UNKNOWN_REASON)

/** A refused start in plain words. */
export function startError(e: unknown): string {
  if (!(e instanceof ApiError)) return e instanceof Error ? e.message : 'The review could not start. Try again.'
  if (e.code === 'review_running') return 'A review is already running.'
  if (e.code === 'no_model') return 'Add a model in Settings to run the reviewer.'
  return Object.hasOwn(REASON, e.code) ? reasonText(e.code) : 'The review could not start. Try again.'
}

const SEVERITY: Record<Severity, string> = { blocker: 'Blocker', major: 'Major', minor: 'Minor', nit: 'Nit' }
export const severityLabel = (severity: Severity): string => SEVERITY[severity]

/** One mode's estimate line, shown before anything starts. */
export function modeText(estimate: DraftEstimate): string {
  if (estimate.mode === 'light') return `Light: up to ${estimate.max_calls} model calls, about 10 to 15 minutes on a local model.`
  return `Full: about ${estimate.likely_calls} model calls, at most ${estimate.max_calls}, up to an hour or more on a local model.`
}

/** The question the full-mode confirm step asks. */
export const fullConfirmText = (estimate: DraftEstimate): string =>
  `This runs about ${estimate.likely_calls} model calls, at most ${estimate.max_calls}. Run it?`

export const startBody = (mode: DraftMode, confirmRemote: boolean, confirmFull: boolean): DraftStart => ({
  mode,
  confirm_remote: confirmRemote,
  confirm_full: confirmFull,
})

/** Queued or running: the only states the dialog polls and shows progress for. */
export const isLive = (review: Pick<DraftReview, 'status'> | null | undefined): boolean =>
  review?.status === 'queued' || review?.status === 'running'

const DISCARD_KEYS = ['dropped_invalid', 'dropped_criterion', 'dropped_quote', 'dropped_wording']
/** Points the model raised that were thrown out (not dedupes, masked reasons or the over-cap tail). */
export const discardedCount = (counts: Record<string, number>): number =>
  DISCARD_KEYS.reduce((n, key) => n + (counts[key] ?? 0), 0)

/** "Light, 1 round" / "Full, 2 rounds" for a finished review. */
export function runSummary(review: Pick<DraftReview, 'mode' | 'counts'>): string {
  const rounds = review.counts.rounds_run ?? 1
  return `${review.mode === 'full' ? 'Full' : 'Light'}, ${rounds} ${rounds === 1 ? 'round' : 'rounds'}`
}
