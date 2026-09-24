import { useState } from 'react'
import { useSearchHits, useUploadHitPdf } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { pageLink } from '@/features/discovery/candidateMeta'
import { copyText } from '@/lib/clipboard'

/** Hits stage-1 marked relevant but with no free PDF found automatically (Task 9/11's `import_hits` leaves these
 * `acquisition_status: 'failed'`). The user finds a copy themselves and uploads it here.
 *
 * Paginated (I7 fix 1): `useSearchHits` defaults to 50 per page, and a run can turn up well over 50 failures
 * (spec P7 — most hits are paywalled), so a "Load more" button fetches the rest instead of silently truncating.
 *
 * Shows the linked ExternalRef's real title/authors/year/venue/doi (I7 fix 2) when there is one, falling back to
 * `normalized_title` for a hit that never matched a ref. */
export function ManualAcquisitionTab({ workspaceId }: { workspaceId: string }) {
  const { data, hasNextPage, isFetchingNextPage, fetchNextPage } = useSearchHits(workspaceId, undefined, 'failed')
  const upload = useUploadHitPdf(workspaceId)
  const [copyError, setCopyError] = useState<string | null>(null)
  const rows = data?.pages.flatMap((page) => page.items) ?? []

  async function copyDoi(doi: string) {
    try {
      await copyText(doi)
      setCopyError(null)
    } catch (error) {
      setCopyError(error instanceof Error ? error.message : 'Could not copy.')
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-3">
      {rows.length === 0 && (
        <p className="text-sm text-muted-foreground">Nothing needs manual acquisition right now.</p>
      )}
      {rows.map((hit) => {
        // `||`, not `??`: an empty-string title (falsy but not null/undefined) must still fall back, not render blank.
        const title = hit.title || hit.normalized_title
        const byline = [hit.authors?.join(', ') || null, hit.year, hit.venue].filter(Boolean).join(' · ')
        // Only doi ever reaches HitOut, so pageLink's other identifiers are always null here — still the same
        // "Open page" logic the References panel uses, just fed less to work with.
        const openPage = pageLink({ doi: hit.doi ?? null, arxiv_id: null, openalex_id: null, s2_id: null, core_id: null })
        return (
          <div key={hit.id} className="flex items-center justify-between gap-3 border-b pb-2 text-sm">
            <div className="min-w-0 flex-1">
              <p className="truncate">{title}</p>
              {byline && <p className="truncate text-xs text-muted-foreground">{byline}</p>}
            </div>
            <a
              href={`https://scholar.google.com/scholar?q=${encodeURIComponent(title)}`}
              target="_blank"
              rel="noreferrer"
            >
              Search by title
            </a>
            {openPage && (
              <a href={openPage} target="_blank" rel="noreferrer">
                Open page
              </a>
            )}
            {hit.doi && (
              <Button type="button" variant="ghost" size="sm" onClick={() => copyDoi(hit.doi!)}>
                Copy DOI
              </Button>
            )}
            <label>
              <span className="sr-only">{`Upload PDF for ${title}`}</span>
              <input
                type="file"
                accept="application/pdf"
                aria-label={`Upload PDF for ${title}`}
                disabled={upload.isPending}
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) upload.mutate({ hitId: hit.id, file })
                }}
              />
            </label>
          </div>
        )
      })}
      {hasNextPage && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isFetchingNextPage}
          onClick={() => fetchNextPage()}
        >
          {isFetchingNextPage ? 'Loading…' : 'Load more'}
        </Button>
      )}
      {upload.isError && (
        <p role="alert" className="text-xs text-destructive">
          {upload.error.message}
        </p>
      )}
      {copyError && (
        <p role="alert" className="text-xs text-destructive">
          {copyError}
        </p>
      )}
    </div>
  )
}
