import { useEffect, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { HitReviewUpdate, SearchRun } from '@/api/client'
import { useImportSearchHits, useNewHitsAvailable, usePatchSearchHit, useRefreshHits, useSearchHits } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { HitContextMenu, HitMenu } from './HitMenu'
import { HitPreview } from './HitPreview'

const ROW_HEIGHT = 44
/** Skimming the list with the mouse shouldn't swap the preview for every row it crosses — same delay PaperList
 * uses for the same reason. */
const HOVER_PREVIEW_DELAY_MS = 150

/** The hit pool for a search run: a virtualized list (rows can run into the thousands) beside a preview of the
 * hovered or focused one (title, byline, abstract — same split as the library's PaperList/PaperPreview), stage-1
 * triage via a right-click menu or a trailing ⋮ button on each row, and a bulk import for hits that already
 * cleared review. `run` is only read here to know whether the worker has found more since the pool was last
 * loaded — the run's own live status is shown elsewhere (SearchTab), unaffected by any of this. */
export function HitTable({ workspaceId, run }: { workspaceId: string; run?: SearchRun }) {
  const { data, hasNextPage, isFetchingNextPage, fetchNextPage } = useSearchHits(workspaceId)
  const importHits = useImportSearchHits(workspaceId)
  const reviewHit = usePatchSearchHit(workspaceId)
  const newHits = useNewHitsAvailable(run)
  const refreshHits = useRefreshHits(workspaceId)
  const parentRef = useRef<HTMLDivElement>(null)
  const hoverTimer = useRef<number | undefined>(undefined)
  const [previewId, setPreviewId] = useState<string | null>(null)

  const rows = data?.pages.flatMap((page) => page.items) ?? []
  // Falls back to the first loaded row, so the panel is never empty on first paint (mirrors PaperList).
  const previewed = rows.find((hit) => hit.id === previewId) ?? rows[0]

  useEffect(() => () => window.clearTimeout(hoverTimer.current), [])

  function preview(id: string, immediate: boolean) {
    window.clearTimeout(hoverTimer.current)
    if (immediate) setPreviewId(id)
    else hoverTimer.current = window.setTimeout(() => setPreviewId(id), HOVER_PREVIEW_DELAY_MS)
  }

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
    // Without this, the virtualizer reports zero virtual items until ResizeObserver fires with the real
    // container size (a first-paint flash of an empty list) — and jsdom has no ResizeObserver at all, so
    // tests would see an empty list forever. A reasonable guess for the panel's usual height fixes both.
    initialRect: { width: 600, height: 600 },
  })
  const virtualItems = virtualizer.getVirtualItems()

  // Data only ever moves into view because the user is scrolled to the bottom of what's loaded — never on a
  // background timer or poll, which doesn't scale once the pool reaches thousands of hits (re-fetching an
  // infinite query re-fetches every already-loaded page; see useNewHitsAvailable's docstring). Two cases at the
  // bottom: a known next page (hasNextPage) just fetches it, same as always. When there is no known next page but
  // the worker has found more since our last real fetch (newHits.available, from the already-polled run status),
  // the cached "no more pages" cursor is stale — pay the one real-refresh cost here, since the user scrolling to
  // the bottom asking for more is exactly the moment it's worth it.
  useEffect(() => {
    const lastItem = virtualItems.at(-1)
    if (!lastItem || lastItem.index < rows.length - 1 || isFetchingNextPage) return
    if (hasNextPage) {
      fetchNextPage()
    } else if (newHits.available) {
      newHits.acknowledge()
      refreshHits()
    }
  }, [virtualItems, hasNextPage, isFetchingNextPage, fetchNextPage, rows.length, newHits, refreshHits])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between border-b px-3 py-2 text-sm">
        <span>{rows.length} in pool</span>
        <Button type="button" size="sm" disabled={importHits.isPending} onClick={() => importHits.mutate(undefined)}>
          Import all with PDF in this filter
        </Button>
      </div>
      {importHits.isError && (
        <p role="alert" className="px-3 py-1 text-xs text-destructive">
          {importHits.error.message}
        </p>
      )}
      {reviewHit.isError && (
        <p role="alert" className="px-3 py-1 text-xs text-destructive">
          {reviewHit.error.message}
        </p>
      )}
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div ref={parentRef} aria-label="Hit pool" className="min-h-0 overflow-auto">
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {virtualItems.map((virtualRow) => {
              const hit = rows[virtualRow.index]
              const onReview = (hitId: string, body: HitReviewUpdate) => reviewHit.mutate({ hitId, body })
              const byline = [hit.authors?.slice(0, 3).join(', '), hit.year].filter(Boolean).join(' · ')
              return (
                <HitContextMenu key={hit.id} hit={hit} onReview={onReview}>
                  <div
                    className="flex w-full items-center gap-2 border-b px-3 text-sm hover:bg-muted"
                    style={{ position: 'absolute', top: virtualRow.start, height: virtualRow.size, width: '100%' }}
                    onMouseEnter={() => preview(hit.id, false)}
                    onFocus={() => preview(hit.id, true)}
                  >
                    <span className="flex-1 truncate">
                      {hit.title ?? hit.normalized_title}
                      {byline && <span className="text-muted-foreground"> · {byline}</span>}
                    </span>
                    <span className="text-xs text-muted-foreground">{hit.stage1_status ?? 'unreviewed'}</span>
                    <HitMenu hit={hit} onReview={onReview} />
                  </div>
                </HitContextMenu>
              )
            })}
          </div>
        </div>
        {/* Desktop only: the preview follows hover and focus, which a touch screen doesn't have — same as PaperPreview. */}
        {previewed && (
          <div className="hidden min-h-0 lg:block">
            <HitPreview hit={previewed} />
          </div>
        )}
      </div>
      {isFetchingNextPage && <div className="border-t px-3 py-1 text-xs text-muted-foreground">Loading more…</div>}
    </div>
  )
}
