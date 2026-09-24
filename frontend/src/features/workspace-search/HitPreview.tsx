import { useState } from 'react'
import type { Hit, HitReviewUpdate } from '@/api/client'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { pageLink } from '@/features/discovery/candidateMeta'
import { copyText } from '@/lib/clipboard'
import { cn } from '@/lib/utils'
import { EXCLUDE_REASONS } from './hitReview'

type ExcludeReason = (typeof EXCLUDE_REASONS)[number]

type Props = {
  hit: Hit
  onReview: (hitId: string, body: HitReviewUpdate) => void
  onUpload: (hitId: string, file: File) => void
  uploadPending: boolean
}

/** The hovered or focused hit's title, byline and abstract, plus the same stage-1 triage HitMenu offers and (for
 * a hit with no PDF yet) the same acquisition options ManualAcquisitionTab offers — same split as the library's
 * PaperList/PaperPreview, but this panel also carries the actions: reading, deciding relevance and getting the
 * PDF are all the same moment here, instead of PaperPreview's read-only "Open in reader" button. HitMenu/
 * HitContextMenu stay available too, for triage without hovering (keyboard, touch, or a quick pass across many
 * rows). A hit whose candidate never matched an ExternalRef (title/authors/year/venue/abstract/doi all null)
 * falls back to the normalized_title every hit always has, and shows nothing else. */
export function HitPreview({ hit, onReview, onUpload, uploadPending }: Props) {
  const title = hit.title || hit.normalized_title
  const byline = [hit.authors?.join(', ') || null, hit.year, hit.venue].filter(Boolean).join(' · ')
  const [reason, setReason] = useState<ExcludeReason | ''>('')
  const [copyError, setCopyError] = useState<string | null>(null)
  // Only doi ever reaches HitOut, so pageLink's other identifiers are always null here — same as
  // ManualAcquisitionTab, just fed less to work with.
  const openPage = pageLink({ doi: hit.doi ?? null, arxiv_id: null, openalex_id: null, s2_id: null, core_id: null })
  const needsAcquisition = hit.acquisition_status !== 'imported' && hit.acquisition_status !== 'manual'

  const markNotRelevant = () => {
    if (!reason) return
    onReview(hit.id, { stage1_status: 'not_relevant', stage1_exclude_reason: reason })
    setReason('')
  }

  async function copyDoi(doi: string) {
    try {
      await copyText(doi)
      setCopyError(null)
    } catch (error) {
      setCopyError(error instanceof Error ? error.message : 'Could not copy.')
    }
  }

  return (
    <aside
      aria-label="Hit preview"
      className={cn('hit-preview flex flex-col gap-2 overflow-y-auto rounded-xl p-4 ring-1 ring-glass-border', glass)}
    >
      <h2 className="font-heading text-lg leading-snug font-semibold wrap-anywhere">{title}</h2>
      {byline && <p className="text-sm text-muted-foreground">{byline}</p>}
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

      {needsAcquisition && (
        <div className="mt-2 flex flex-col gap-2 border-t border-glass-border pt-3">
          <p className="text-xs font-medium text-muted-foreground">Get the PDF</p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <a
              href={`https://scholar.google.com/scholar?q=${encodeURIComponent(title)}`}
              target="_blank"
              rel="noreferrer"
              className="text-primary hover:underline"
            >
              Search by title
            </a>
            {openPage && (
              <a href={openPage} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                Open page
              </a>
            )}
            {hit.doi && (
              <Button type="button" variant="ghost" size="sm" className="h-auto p-0 text-xs" onClick={() => copyDoi(hit.doi!)}>
                Copy DOI
              </Button>
            )}
          </div>
          <label className="w-fit">
            <span className="sr-only">{`Upload PDF for ${title}`}</span>
            <input
              type="file"
              accept="application/pdf"
              aria-label={`Upload PDF for ${title}`}
              disabled={uploadPending}
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) onUpload(hit.id, file)
              }}
            />
          </label>
          {copyError && (
            <p role="alert" className="text-xs text-destructive">
              {copyError}
            </p>
          )}
        </div>
      )}
    </aside>
  )
}
