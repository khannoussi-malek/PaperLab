import { useState } from 'react'
import type { Hit, HitReviewUpdate } from '@/api/client'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { EXCLUDE_REASONS } from './hitReview'

type ExcludeReason = (typeof EXCLUDE_REASONS)[number]

/** The hovered or focused hit's title, byline and abstract, plus the same stage-1 triage HitMenu offers — same
 * split as the library's PaperList/PaperPreview, but this panel also carries the actions: reading the abstract
 * and deciding relevance are the same moment here, unlike PaperPreview's read-only "Open in reader" button.
 * HitMenu/HitContextMenu stay available too, for triage without hovering (keyboard, touch, or a quick pass
 * across many rows). A hit whose candidate never matched an ExternalRef (title/authors/year/venue/abstract all
 * null) falls back to the normalized_title every hit always has, and shows nothing else. */
export function HitPreview({ hit, onReview }: { hit: Hit; onReview: (hitId: string, body: HitReviewUpdate) => void }) {
  const byline = [hit.authors?.join(', '), hit.year, hit.venue].filter(Boolean).join(' · ')
  const [reason, setReason] = useState<ExcludeReason | ''>('')

  const markNotRelevant = () => {
    if (!reason) return
    onReview(hit.id, { stage1_status: 'not_relevant', stage1_exclude_reason: reason })
    setReason('')
  }

  return (
    <aside
      aria-label="Hit preview"
      className={cn('hit-preview flex flex-col gap-2 overflow-y-auto rounded-xl p-4 ring-1 ring-glass-border', glass)}
    >
      <h2 className="font-heading text-lg leading-snug font-semibold wrap-anywhere">{hit.title ?? hit.normalized_title}</h2>
      {byline && <p className="text-sm text-muted-foreground">{byline}</p>}
      {hit.doi && (
        <a
          href={`https://doi.org/${encodeURIComponent(hit.doi)}`}
          target="_blank"
          rel="noreferrer"
          className="w-fit text-xs text-primary hover:underline"
        >
          doi:{hit.doi}
        </a>
      )}
      {hit.abstract ? (
        <p className="mt-2 text-sm whitespace-pre-line">{hit.abstract}</p>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">No abstract available for this hit.</p>
      )}

      <div className="mt-2 flex flex-col gap-2 border-t border-glass-border pt-3">
        <div className="flex gap-2">
          <Button type="button" size="sm" onClick={() => onReview(hit.id, { stage1_status: 'relevant' })}>
            Relevant
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => onReview(hit.id, { stage1_status: 'maybe' })}>
            Maybe
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="hit-preview-reason" className="sr-only">
            Exclusion reason
          </label>
          <select
            id="hit-preview-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value as ExcludeReason | '')}
            aria-label="Exclusion reason"
            className="h-8 flex-1 rounded-lg border bg-background px-2 text-sm"
          >
            <option value="">Select a reason…</option>
            {EXCLUDE_REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <Button type="button" size="sm" variant="destructive" disabled={!reason} onClick={markNotRelevant}>
            Not relevant
          </Button>
        </div>
      </div>
    </aside>
  )
}
