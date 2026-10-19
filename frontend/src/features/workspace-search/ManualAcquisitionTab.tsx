import { useState } from 'react'
import { codeInWords } from '@/lib/errorWords'
import { useSearchHits, useUploadHitPdf } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { pageLink } from '@/features/discovery/candidateMeta'
import { copyText } from '@/lib/clipboard'
import { FindFreeCopy, UploadPdfButton } from '@/features/library/GetPdfActions'
import { LoadError } from '@/features/library/ErrorAlert'
import { EmptyState, TabSkeleton } from '@/features/workspaces/TabStates'

const WHY_HERE = 'Relevant papers land here only when no free PDF was found for them.'

/** Hits stage-1 marked relevant but with no free PDF found automatically (Task 9/11's `import_hits` leaves these
 * `acquisition_status: 'failed'`). The user finds a copy themselves and uploads it here.
 *
 * Paginated (I7 fix 1): `useSearchHits` defaults to 50 per page, and a run can turn up well over 50 failures
 * (spec P7 — most hits are paywalled), so a "Load more" button fetches the rest instead of silently truncating.
 *
 * Shows the linked ExternalRef's real title/authors/year/venue/doi (I7 fix 2) when there is one, falling back to
 * `normalized_title` for a hit that never matched a ref. */
export function ManualAcquisitionTab({ workspaceId }: { workspaceId: string }) {
  const failed = useSearchHits(workspaceId, undefined, 'failed')
  const awaiting = useSearchHits(workspaceId, undefined, 'awaiting_pdf')
  const { isError, error, refetch, isFetchingNextPage } = failed
  const isPending = failed.isPending || awaiting.isPending
  const hasNextPage = failed.hasNextPage || awaiting.hasNextPage
  // Pages are fetched together: "Load more" asks each list that has more.
  const fetchNextPage = () => Promise.all([failed.hasNextPage && failed.fetchNextPage(), awaiting.hasNextPage && awaiting.fetchNextPage()])
  const upload = useUploadHitPdf(workspaceId)
  const [copyError, setCopyError] = useState<string | null>(null)
  const rows = [...(failed.data?.pages ?? []), ...(awaiting.data?.pages ?? [])].flatMap((page) => page.items)

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
      {isPending && <TabSkeleton label="Loading papers to fetch" />}
      {isError && <LoadError message={error.message} onRetry={() => void refetch()} />}
      {!isPending && !isError && rows.length === 0 && (
        <EmptyState title="Nothing to fetch by hand">{WHY_HERE}</EmptyState>
      )}
      {rows.length > 0 && (
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-medium">
            {hasNextPage && 'At least '}
            {rows.length} relevant {rows.length === 1 ? 'paper needs' : 'papers need'} a PDF
          </h2>
          <p className="max-w-prose text-sm text-muted-foreground">{WHY_HERE}</p>
        </div>
      )}
      {rows.map((hit) => {
        // `||`, not `??`: an empty-string title (falsy but not null/undefined) must still fall back, not render blank.
        const title = hit.title || hit.normalized_title
        const byline = [hit.authors?.join(', ') || null, hit.year, hit.venue].filter(Boolean).join(' · ')
        // Only doi ever reaches HitOut, so pageLink's other identifiers are always null here — still the same
        // "Open page" logic the References panel uses, just fed less to work with.
        const openPage = pageLink({ doi: hit.doi ?? null, external_ids: {} })
        return (
          <div key={hit.id} className="flex flex-wrap items-center justify-between gap-3 border-b pb-2 text-sm">
            <div className="min-w-0 flex-1">
              <p className="truncate">{title}</p>
              {hit.acquisition_status === 'awaiting_pdf' && (
                <p className="text-xs text-muted-foreground">Saved without a PDF</p>
              )}
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
            <UploadPdfButton
              title={title}
              disabled={upload.isPending}
              onPick={(file, onFail) => upload.mutate({ hitId: hit.id, file }, { onError: onFail })}
            />
            {hit.acquisition_status === 'awaiting_pdf' && hit.paper_id && <FindFreeCopy paperId={hit.paper_id} />}
          </div>
        )
      })}
      {hasNextPage && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isFetchingNextPage || awaiting.isFetchingNextPage}
          onClick={() => fetchNextPage()}
        >
          {isFetchingNextPage || awaiting.isFetchingNextPage ? 'Loading…' : 'Load more'}
        </Button>
      )}
      {upload.isError && (
        <p role="alert" className="text-xs text-destructive">
          {codeInWords(upload.error.message)}
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
