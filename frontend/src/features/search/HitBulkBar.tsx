import { CircleHelp, CircleX, Sparkles, ThumbsUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Term } from '@/components/Term'
import { EXCLUDE_REASONS, reasonLabel } from '@/features/search/hitReview'
import type { ExcludeReason } from '@/features/search/useHitSelection'

/** The bar shown while rows are checked: bulk relevance marks, accept suggestions, and bulk exclusion. */
export function HitBulkBar({
  count,
  bulkPending,
  acceptPending,
  bulkReason,
  onBulkReasonChange,
  onMark,
  onAccept,
  onMarkNotRelevant,
  onClear,
}: {
  count: number
  bulkPending: boolean
  acceptPending: boolean
  bulkReason: ExcludeReason | ''
  onBulkReasonChange: (reason: ExcludeReason | '') => void
  onMark: (stage1_status: 'relevant' | 'maybe') => void
  onAccept: () => void
  onMarkNotRelevant: () => void
  onClear: () => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-muted/50 px-3 py-2 text-sm">
      <span className="font-medium">{count} selected</span>
      <Button type="button" size="sm" disabled={bulkPending} onClick={() => onMark('relevant')}>
        <ThumbsUp aria-hidden />
        Mark relevant
      </Button>
      <Button type="button" size="sm" variant="outline" disabled={bulkPending} onClick={() => onMark('maybe')}>
        <CircleHelp aria-hidden />
        Mark maybe
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={acceptPending}
        onClick={onAccept}
      >
        <Sparkles aria-hidden />
        Accept AI suggestions
      </Button>
      <Term term="aiSuggestion"><span className="sr-only">What is an AI suggestion?</span></Term>
      <label htmlFor="bulk-exclude-reason" className="sr-only">
        Exclusion reason for selected results
      </label>
      <select
        id="bulk-exclude-reason"
        value={bulkReason}
        onChange={(event) => onBulkReasonChange(event.target.value as ExcludeReason | '')}
        aria-label="Exclusion reason for selected results"
        className="h-8 rounded-lg border bg-background px-2 text-sm"
      >
        <option value="">Select a reason…</option>
        {EXCLUDE_REASONS.map((r) => (
          <option key={r} value={r}>
            {reasonLabel(r)}
          </option>
        ))}
      </select>
      <Button
        type="button"
        size="sm"
        variant="destructive"
        disabled={!bulkReason || bulkPending}
        onClick={onMarkNotRelevant}
      >
        <CircleX aria-hidden />
        Mark not relevant
      </Button>
      <Button type="button" size="sm" variant="ghost" className="text-muted-foreground" onClick={onClear}>
        Clear selection
      </Button>
    </div>
  )
}
