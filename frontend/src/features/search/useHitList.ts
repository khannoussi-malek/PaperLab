import { useEffect, useLayoutEffect, type RefObject } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { Hit } from '@/entities'
import type { useNewHitsAvailable } from '@/services/queries'
import { useMediaQuery } from '@/lib/useMediaQuery'
import type { HitSort } from '@/features/search/hitSort'
import { NARROW, ROW_HEIGHT, ROW_HEIGHT_NARROW } from '@/features/search/hitTableLayout'

/** The virtualized hit list's scroll, keyboard selection, and fetch-more-at-the-bottom behaviour. */
export function useHitList({
  visibleRows,
  sort,
  previewedId,
  setPreviewId,
  parentRef,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  newHits,
  refreshHits,
}: {
  visibleRows: Hit[]
  sort: HitSort
  previewedId: string | undefined
  setPreviewId: (hitId: string) => void
  parentRef: RefObject<HTMLDivElement | null>
  hasNextPage: boolean
  isFetchingNextPage: boolean
  fetchNextPage: () => unknown
  newHits: ReturnType<typeof useNewHitsAvailable>
  refreshHits: () => unknown
}) {
  const narrow = useMediaQuery(NARROW)
  const virtualizer = useVirtualizer({
    count: visibleRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => (narrow ? ROW_HEIGHT_NARROW : ROW_HEIGHT),
    overscan: 10,
    // Without this, the virtualizer reports zero virtual items until ResizeObserver fires with the real
    // container size (a first-paint flash of an empty list) — and jsdom has no ResizeObserver at all, so
    // tests would see an empty list forever. A reasonable guess for the panel's usual height fixes both.
    initialRect: { width: 600, height: 600 },
  })
  useLayoutEffect(() => virtualizer.measure(), [narrow, virtualizer])
  const virtualItems = virtualizer.getVirtualItems()

  // ↑/↓ moves the selected row by one, wrapping never — the top/bottom just stop. Works from the filter box too
  // (arrow keys do nothing useful in a single-line input, so hijacking them here doesn't lose anything), and
  // scrolls the new selection into view since it can be off-screen in a long, virtualized list.
  function moveSelection(direction: 1 | -1, event: React.KeyboardEvent) {
    if (visibleRows.length === 0) return
    event.preventDefault()
    const currentIndex = visibleRows.findIndex((hit) => hit.id === previewedId)
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
    if (sort === 'ranked') return // ranked order has its own, unpaginated query — nothing more to page in
    const lastItem = virtualItems.at(-1)
    if (!lastItem || lastItem.index < visibleRows.length - 1 || isFetchingNextPage) return
    if (hasNextPage) {
      fetchNextPage()
    } else if (newHits.available) {
      newHits.acknowledge()
      refreshHits()
    }
  }, [sort, virtualItems, hasNextPage, isFetchingNextPage, fetchNextPage, visibleRows.length, newHits, refreshHits])

  return { narrow, virtualizer, virtualItems, onListKeyDown }
}
