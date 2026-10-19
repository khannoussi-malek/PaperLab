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

/** Hits stage-1 marked relevant but with no PDF yet: no free PDF was found (`acquisition_status: 'failed'`), or the
 * paper was saved without one (`'awaiting_pdf'`, listed apart as "Saved without a PDF"). The user finds a copy
 * themselves and uploads it here, or has PaperLab look for a free one for a saved paper.
 *
 * Paginated (I7 fix 1): `useSearchHits` defaults to 50 per page, and a run can turn up well over 50 failures
 * (spec P7 — most hits are paywalled), so a "Load more" button fetches the rest instead of silently truncating.
 *
 * Shows the linked ExternalRef's real title/authors/year/venue/doi (I7 fix 2) when there is one, falling back to
 * `normalized_title` for a hit that never matched a ref. */
export function ManualAcquisitionTab({ workspaceId }: { workspaceId: string }) {
  const failed = useSearchHits(workspaceId, undefined, 'failed')
  const awaiting = useSearchHits(workspaceId, undefined, 'awaiting_pdf')
  const { isFetchingNextPage } = failed
  const loadFailed = failed.isError ? failed : awaiting.isError ? awaiting : null
  const isPending = failed.isPending || awaiting.isPending
  const hasNextPage = failed.hasNextPage || awaiting.hasNextPage
  // Pages are fetched together: "Load more" asks each list that has more.
  const fetchNextPage = () => Promise.all([failed.hasNextPage && failed.fetchNextPage(), awaiting.hasNextPage && awaiting.fetchNextPage()])
  const upload = useUploadHitPdf(workspaceId)
  const [copyError, setCopyError] = useState<string | null>(null)
  // Two groups, so loading more failed hits never moves the saved-without-a-PDF rows.
  const failedRows = failed.data?.pages.flatMap((page) => page.items) ?? []
  const awaitingRows = awaiting.data?.pages.flatMap((page) => page.items) ?? []
  const rows = [...failedRows, ...awaitingRows]

  async function copyDoi(doi: string) {
    try {
      await copyText(doi)
      setCopyError(null)
    } catch (error) {
      setCopyError(error instanceof Error ? error.message : 'Could not copy.')
    }
  }

  const renderRow = (hit: (typeof rows)[number]) => {
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
        {hit.acquisition_status === 'awaiting_pdf' && hit.paper_id && <FindFreeCopy paperId={hit.paper_id} title={title} />}
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-3">
      {isPending && <TabSkeleton label="Loading papers to fetch" />}
      {loadFailed && <LoadError message={loadFailed.error?.message ?? 'Could not load papers.'} onRetry={() => void loadFailed.refetch()} />}
      {!isPending && !loadFailed && rows.length === 0 && (
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
      {failedRows.map(renderRow)}
      {awaitingRows.length > 0 && (
        <section aria-labelledby="saved-without-pdf" className="flex flex-col gap-1">
          <h3 id="saved-without-pdf" className="text-sm font-medium">Saved without a PDF</h3>
          {awaitingRows.map(renderRow)}
        </section>
      )}
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
