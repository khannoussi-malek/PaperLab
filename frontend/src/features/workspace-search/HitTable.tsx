import { useEffect, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useImportSearchHits, usePatchSearchHit, useSearchHits } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { HitContextMenu, HitMenu } from './HitMenu'

const ROW_HEIGHT = 44

/** The hit pool for a search run: a virtualized list (rows can run into the thousands) with stage-1 triage via
 * a right-click menu or a trailing ⋮ button on each row, and a bulk import for hits that already cleared review. */
export function HitTable({ workspaceId }: { workspaceId: string }) {
  const { data, hasNextPage, isFetchingNextPage, fetchNextPage } = useSearchHits(workspaceId)
  const importHits = useImportSearchHits(workspaceId)
  const reviewHit = usePatchSearchHit(workspaceId)
  const parentRef = useRef<HTMLDivElement>(null)

  const rows = data?.pages.flatMap((page) => page.items) ?? []

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

  // Once the rendered range reaches the last loaded row, fetch the next page. An effect (not a render-time call,
  // as the sketch had it) — fetchNextPage triggers a query state update, and doing that mid-render risks React
  // warning about updating state while rendering.
  useEffect(() => {
    const lastItem = virtualItems.at(-1)
    if (lastItem && lastItem.index >= rows.length - 1 && hasNextPage && !isFetchingNextPage) {
      fetchNextPage()
    }
  }, [virtualItems, hasNextPage, isFetchingNextPage, fetchNextPage, rows.length])

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
      <div ref={parentRef} className="min-h-0 flex-1 overflow-auto">
        <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualItems.map((virtualRow) => {
            const hit = rows[virtualRow.index]
            return (
              <HitContextMenu key={hit.id} hitId={hit.id} onReview={(hitId, body) => reviewHit.mutate({ hitId, body })}>
                <div
                  className="flex w-full items-center gap-2 border-b px-3 text-sm hover:bg-muted"
                  style={{ position: 'absolute', top: virtualRow.start, height: virtualRow.size, width: '100%' }}
                >
                  <span className="flex-1 truncate">{hit.normalized_title}</span>
                  <span className="text-xs text-muted-foreground">{hit.stage1_status ?? 'unreviewed'}</span>
                  <HitMenu hitId={hit.id} onReview={(hitId, body) => reviewHit.mutate({ hitId, body })} />
                </div>
              </HitContextMenu>
            )
          })}
        </div>
      </div>
      {isFetchingNextPage && <div className="border-t px-3 py-1 text-xs text-muted-foreground">Loading more…</div>}
    </div>
  )
}
