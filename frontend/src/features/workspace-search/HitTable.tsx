import { useEffect, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { Hit, HitReviewUpdate, SearchRun } from '@/api/client'
import {
  totalRawFound,
  useClearSearchHits,
  useImportAllHits,
  useImportSearchHits,
  useNewHitsAvailable,
  usePatchSearchHit,
  useRefreshHits,
  useSearchHits,
  useUploadHitPdf,
} from '@/api/queries'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { HitContextMenu, HitMenu } from './HitMenu'
import { sourceLabel } from './hitReview'
import { HitPreview } from './HitPreview'

const ROW_HEIGHT = 44

function hasPdfOrAbstract(hit: Hit): boolean {
  return hit.acquisition_status === 'imported' || hit.acquisition_status === 'manual' || Boolean(hit.abstract)
}

/** Matches the filter box against title and abstract — whichever provider supplied it, a search term can turn up
 * in either, and a title-only match misses a hit whose title doesn't mention it but whose abstract does. */
function matchesFilter(hit: Hit, filter: string): boolean {
  const title = (hit.title ?? hit.normalized_title).toLowerCase()
  const abstract = hit.abstract?.toLowerCase() ?? ''
  return title.includes(filter) || abstract.includes(filter)
}

/** The hit pool for a search run: a virtualized list (rows can run into the thousands) beside a preview of the
 * selected one (title, byline, abstract — same split as the library's PaperList/PaperPreview). Rows with an
 * abstract to read or a PDF already in the corpus sort first (`hasPdfOrAbstract`) — those are the ones a reader
 * can actually judge; a bare title with neither is the hardest to screen. Selection moves by clicking a row or
 * with the ↑/↓ arrow keys (from the row list or the filter box) — not hover, so skimming the list with the mouse
 * doesn't fight with reading the panel. A filter box narrows the already-loaded rows by title OR abstract
 * (`matchesFilter`) client-side (no new request — see `useSearchHits`, still the full, unfiltered query
 * underneath) — whichever provider supplied the abstract, a term can turn up there even when the title doesn't
 * mention it. Stage-1 triage
 * is via a right-click menu or a trailing ⋮ button on each row, and there are two ways to get a PDF: one hit at a
 * time from the preview panel's "Add PDF" (fetching a PDF starts ingestion — chunking, embedding — for that paper,
 * so this is the cheap default), or "Import all with PDF in this filter" when the user has decided that cost is
 * worth paying for everything currently in view at once. "Clear old results" is the other direction — every
 * search a workspace has ever run lands in this same shared pool, with no built-in way to remove anything, so
 * this wipes every not-yet-imported hit back to empty (confirmed first — it's destructive) when the accumulated
 * history no longer matters; already-imported papers are untouched. `run` is read for two things: whether the worker has
 * found more since the pool was last loaded (the run's own live status is shown elsewhere, SearchTab, unaffected
 * by any of this), and the live "N found so far" count — the raw, pre-dedup total every source has turned up
 * (`totalRawFound`), distinct from "in pool," which is the de-duplicated count of what's actually been loaded. */
export function HitTable({ workspaceId, run }: { workspaceId: string; run?: SearchRun }) {
  const { data, hasNextPage, isFetchingNextPage, fetchNextPage } = useSearchHits(workspaceId)
  const importHits = useImportSearchHits(workspaceId)
  const importAllHits = useImportAllHits(workspaceId)
  const clearHits = useClearSearchHits(workspaceId)
  const reviewHit = usePatchSearchHit(workspaceId)
  const uploadHitPdf = useUploadHitPdf(workspaceId)
  const newHits = useNewHitsAvailable(run)
  const refreshHits = useRefreshHits(workspaceId)
  const parentRef = useRef<HTMLDivElement>(null)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [filterText, setFilterText] = useState('')

  const rows = data?.pages.flatMap((page) => page.items) ?? []
  const rawFound = totalRawFound(run)
  const filter = filterText.trim().toLowerCase()
  const filteredRows = filter ? rows.filter((hit) => matchesFilter(hit, filter)) : rows
  // A hit with an abstract to read or a PDF already in the corpus is the one worth looking at first — a bare
  // title with neither is the hardest to judge relevance from. Stable sort (native since ES2019), so hits within
  // each group keep their existing (first_seen_at, id) order from the server.
  const visibleRows = filteredRows
    .slice()
    .sort((a, b) => Number(hasPdfOrAbstract(b)) - Number(hasPdfOrAbstract(a)))
  // Falls back to the first loaded row, so the panel is never empty on first paint (mirrors PaperList) — and to
  // whichever row is first once a filter drops the previously selected one out of view.
  const previewed = visibleRows.find((hit) => hit.id === previewId) ?? visibleRows[0]

  const virtualizer = useVirtualizer({
    count: visibleRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
    // Without this, the virtualizer reports zero virtual items until ResizeObserver fires with the real
    // container size (a first-paint flash of an empty list) — and jsdom has no ResizeObserver at all, so
    // tests would see an empty list forever. A reasonable guess for the panel's usual height fixes both.
    initialRect: { width: 600, height: 600 },
  })
  const virtualItems = virtualizer.getVirtualItems()
  const onReview = (hitId: string, body: HitReviewUpdate) => reviewHit.mutate({ hitId, body })

  // ↑/↓ moves the selected row by one, wrapping never — the top/bottom just stop. Works from the filter box too
  // (arrow keys do nothing useful in a single-line input, so hijacking them here doesn't lose anything), and
  // scrolls the new selection into view since it can be off-screen in a long, virtualized list.
  function moveSelection(direction: 1 | -1, event: React.KeyboardEvent) {
    if (visibleRows.length === 0) return
    event.preventDefault()
    const currentIndex = visibleRows.findIndex((hit) => hit.id === previewed?.id)
    const nextIndex = Math.min(Math.max(currentIndex + direction, 0), visibleRows.length - 1)
    setPreviewId(visibleRows[nextIndex].id)
    virtualizer.scrollToIndex(nextIndex, { align: 'auto' })
  }

  function onListKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'ArrowDown') moveSelection(1, event)
    else if (event.key === 'ArrowUp') moveSelection(-1, event)
  }

  // Data only ever moves into view because the user is scrolled to the bottom of what's loaded — never on a
  // background timer or poll, which doesn't scale once the pool reaches thousands of hits (re-fetching an
  // infinite query re-fetches every already-loaded page; see useNewHitsAvailable's docstring). Two cases at the
  // bottom: a known next page (hasNextPage) just fetches it, same as always. When there is no known next page but
  // the worker has found more since our last real fetch (newHits.available, from the already-polled run status),
  // the cached "no more pages" cursor is stale — pay the one real-refresh cost here, since the user scrolling to
  // the bottom asking for more is exactly the moment it's worth it. Keyed off the *filtered* list's own bottom —
  // a filter that's currently showing only a few matches should still be able to page in more of the pool looking
  // for further matches, the same way scrolling the unfiltered list does.
  useEffect(() => {
    const lastItem = virtualItems.at(-1)
    if (!lastItem || lastItem.index < visibleRows.length - 1 || isFetchingNextPage) return
    if (hasNextPage) {
      fetchNextPage()
    } else if (newHits.available) {
      newHits.acknowledge()
      refreshHits()
    }
  }, [virtualItems, hasNextPage, isFetchingNextPage, fetchNextPage, visibleRows.length, newHits, refreshHits])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between gap-3 border-b px-3 py-2 text-sm">
        <label className="flex flex-1 items-center gap-2">
          <span className="sr-only">Search hits</span>
          <input
            type="text"
            value={filterText}
            onChange={(event) => setFilterText(event.target.value)}
            onKeyDown={onListKeyDown}
            placeholder="Search by title or abstract…"
            aria-label="Search hits"
            className="h-8 w-full max-w-xs rounded-lg border bg-background px-2 text-sm"
          />
        </label>
        <span className="shrink-0 text-muted-foreground">
          {rawFound !== undefined && `${rawFound} found so far · `}
          {filter ? `${visibleRows.length} of ${rows.length} in pool` : `${rows.length} in pool`}
        </span>
        <Button type="button" size="sm" disabled={importAllHits.isPending} onClick={() => importAllHits.mutate()}>
          Import all with PDF in this filter
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={clearHits.isPending}
          onClick={() => {
            if (window.confirm('Clear every hit not yet imported? Papers already in your corpus stay untouched.')) {
              clearHits.mutate()
            }
          }}
        >
          Clear old results
        </Button>
      </div>
      {importHits.isError && (
        <p role="alert" className="px-3 py-1 text-xs text-destructive">
          {importHits.error.message}
        </p>
      )}
      {importAllHits.isError && (
        <p role="alert" className="px-3 py-1 text-xs text-destructive">
          {importAllHits.error.message}
        </p>
      )}
      {clearHits.isError && (
        <p role="alert" className="px-3 py-1 text-xs text-destructive">
          {clearHits.error.message}
        </p>
      )}
      {/* A "failed" import is a resolved response (see useImportSearchHits), not a rejected mutation — no free
          copy was found automatically, which isn't an error so much as a cue to use the manual options already
          in the preview panel. */}
      {importHits.isSuccess && importHits.data.failed > 0 && (
        <p role="status" className="px-3 py-1 text-xs text-muted-foreground">
          No PDF found automatically for that paper — try the options below, or upload one.
        </p>
      )}
      {reviewHit.isError && (
        <p role="alert" className="px-3 py-1 text-xs text-destructive">
          {reviewHit.error.message}
        </p>
      )}
      {uploadHitPdf.isError && (
        <p role="alert" className="px-3 py-1 text-xs text-destructive">
          {uploadHitPdf.error.message}
        </p>
      )}
      {filter && visibleRows.length === 0 && (
        <p className="px-3 py-1 text-xs text-muted-foreground">No hits match “{filterText.trim()}”.</p>
      )}
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div
          ref={parentRef}
          aria-label="Hit pool"
          tabIndex={0}
          onKeyDown={onListKeyDown}
          className="min-h-0 overflow-auto outline-none"
        >
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {virtualItems.map((virtualRow) => {
              const hit = visibleRows[virtualRow.index]
              const byline = [hit.authors?.slice(0, 3).join(', '), hit.year].filter(Boolean).join(' · ')
              const selected = hit.id === previewed?.id
              return (
                <HitContextMenu key={hit.id} hit={hit} onReview={onReview}>
                  <div
                    className={cn(
                      'flex w-full cursor-pointer items-center gap-2 border-b px-3 text-sm hover:bg-muted',
                      selected && 'bg-muted',
                    )}
                    style={{ position: 'absolute', top: virtualRow.start, height: virtualRow.size, width: '100%' }}
                    aria-selected={selected}
                    onClick={() => setPreviewId(hit.id)}
                    onFocus={() => setPreviewId(hit.id)}
                  >
                    <span className="flex-1 truncate">
                      {hit.title ?? hit.normalized_title}
                      {byline && <span className="text-muted-foreground"> · {byline}</span>}
                    </span>
                    {hit.sources[0] && (
                      <span className="shrink-0 rounded-full border px-1.5 py-0.5 text-xs text-muted-foreground">
                        {sourceLabel(hit.sources[0])}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground">{hit.stage1_status ?? 'unreviewed'}</span>
                    <HitMenu hit={hit} onReview={onReview} />
                  </div>
                </HitContextMenu>
              )
            })}
          </div>
        </div>
        {/* Desktop only: the preview panel follows the click/arrow-key selection, which a touch screen doesn't
            have arrow keys for anyway — same split as PaperPreview. */}
        {previewed && (
          <div className="hidden min-h-0 lg:block">
            <HitPreview
              hit={previewed}
              onReview={onReview}
              onAddPdf={(hitId) => importHits.mutate([hitId])}
              addPdfPending={importHits.isPending}
              onUpload={(hitId, file) => uploadHitPdf.mutate({ hitId, file })}
              uploadPending={uploadHitPdf.isPending}
            />
          </div>
        )}
      </div>
      {isFetchingNextPage && <div className="border-t px-3 py-1 text-xs text-muted-foreground">Loading more…</div>}
    </div>
  )
}
