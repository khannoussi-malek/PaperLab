import type { DraftReview } from '@/api/client'
import { discardedCount, reasonText, runSummary, severityLabel } from './draftReviewModel'

const SEVERITY_CLASS: Record<DraftReview['issues'][number]['severity'], string> = {
  blocker: 'font-medium text-destructive',
  major: 'font-medium text-destructive',
  minor: 'font-medium',
  nit: 'text-muted-foreground',
}
const NO_ISSUES = "No issues found. This is a model's read, not a guarantee."

/** A finished (or failed, or interrupted) review: its issues with their quotes and criteria, and what was dismissed. */
export function DraftReviewResult({ review }: { review: DraftReview }) {
  if (review.status === 'failed') return <p className="text-sm">{reasonText(review.reason)}</p>
  if (review.status === 'interrupted') return <p className="text-sm">The review was interrupted. Start again to run it.</p>
  if (review.status !== 'done') return null
  const discarded = discardedCount(review.counts)
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">{runSummary(review)}</p>
      {(review.counts.parts ?? 1) > 1 && (
        <p className="text-sm">{`Reviewed in ${review.counts.parts} parts. A reviewer saw one part at a time, so an issue may already be handled in another part.`}</p>
      )}
      {review.issues.length === 0
        ? <p className="text-sm">{NO_ISSUES}</p>
        : (
          <ol aria-label="Issues" className="space-y-3">
            {review.issues.map((issue) => (
              <li key={issue.id} className="space-y-1.5 rounded-md border border-border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={SEVERITY_CLASS[issue.severity]}>{severityLabel(issue.severity)}</span>
                  <span className="text-muted-foreground">{issue.section}</span>
                </div>
                <p>{issue.summary}</p>
                <blockquote className="border-l-2 border-border pl-3 font-mono text-xs">{issue.quote}</blockquote>
                <p><span className="font-medium">Done when</span> <span>{issue.close_criterion}</span></p>
                <p className="text-xs text-muted-foreground">{`${issue.file}:${issue.line}`}</p>
              </li>
            ))}
          </ol>
        )}
      {review.refuted.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">{`Dismissed by the skeptic (${review.refuted.length})`}</summary>
          <ul className="mt-2 space-y-2">
            {review.refuted.map((r, i) => (
              <li key={i} className="space-y-0.5">
                <p>{r.summary}</p>
                <p className="text-xs text-muted-foreground">{r.reason}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
      {discarded > 0 && (
        <p className="text-xs text-muted-foreground">{`${discarded} model points were discarded (no exact quote, no close criterion, or wording)`}</p>
      )}
    </div>
  )
}
