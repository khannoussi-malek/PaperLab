import { useEffect, useRef, useState, type CSSProperties } from 'react'
import type { HitReviewUpdate, SearchRun, SavedSearchInbox } from '@/entities'
import { totalRawFound, useAcceptSuggestions, useBulkPatchSearchHits, useClearSearchHits, useImportAllHits, useImportSearchHits, useNewHitsAvailable, usePatchSearchHit, useRankedHits, useRefreshHits, useSearchHits, useSnowball, useUploadHitPdf } from '@/services/queries'
import { PanelResizeHandle } from '@/components/PanelResizeHandle'
import { loadPanelWidth, panelTrack, savePanelWidth } from '@/components/panelWidth'
import { Button } from '@/components/ui/button'
import { browserStorage } from '@/components/highlightColors'
import { cn } from '@/lib/utils'
import { matchesFilter } from '@/features/search/hitReview'
import { loadHitSort, saveHitSort, type HitSort } from '@/features/search/hitSort'
import { HitPreview } from '@/features/search/HitPreview'
import { RankSortBar } from '@/features/search/RankSortBar'
import { LoadError } from '@/components/ErrorAlert'
import { EmptyState, TabSkeleton } from '@/features/workspaces/TabStates'
import { HitBulkBar } from '@/features/search/HitBulkBar'
import { HitRow } from '@/features/search/HitRow'
import { HitToolbar } from '@/features/search/HitToolbar'
import { useHitSelection } from '@/features/search/useHitSelection'
import { useHitList } from '@/features/search/useHitList'
import { hitStatusMessage } from '@/features/search/hitTableStatus'
import { HIT_PREVIEW, PANE_PADDING_PX, sortVisibleRows } from '@/features/search/hitTableLayout'

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
 * so this is the cheap default), or "Import N relevant results" when the user has decided that cost is
 * worth paying for everything currently in view at once. "Clear old results" is the other direction — every
 * search a workspace has ever run lands in this same shared pool, with no built-in way to remove anything, so
 * this wipes every not-yet-imported hit back to empty (confirmed first — it's destructive) when the accumulated
 * history no longer matters; already-imported papers are untouched. `run` is read for two things: whether the worker has
 * found more since the pool was last loaded (the run's own live status is shown elsewhere, SearchTab, unaffected
 * by any of this), and the live "N found so far" count — the raw, pre-dedup total every source has turned up
 * (`totalRawFound`), distinct from "in pool," which is the de-duplicated count of what's actually been loaded. */
export function HitTable({
  workspaceId,
  run,
  inbox,
  onLeaveInbox,
}: {
  workspaceId: string
  run?: SearchRun
  /** A saved search's new finds (M7.6): the list narrows to them, in found order. */
  inbox?: SavedSearchInbox
  onLeaveInbox?: () => void
}) {
  const [sort, setSort] = useState<HitSort>(() => loadHitSort(browserStorage(), workspaceId))
  const [minRelevance, setMinRelevance] = useState<number | null>(null)
  const { data, isPending, isError, error, refetch, hasNextPage, isFetchingNextPage, fetchNextPage } = useSearchHits(workspaceId, undefined, undefined, {
    sort: sort === 'ai' ? 'ai' : undefined,
    minRelevance: sort === 'ranked' ? undefined : (minRelevance ?? undefined),
    inbox,
  })
  const acceptSuggestions = useAcceptSuggestions(workspaceId)
  const importHits = useImportSearchHits(workspaceId)
  const importAllHits = useImportAllHits(workspaceId)
  const clearHits = useClearSearchHits(workspaceId)
  const reviewHit = usePatchSearchHit(workspaceId)
  const uploadHitPdf = useUploadHitPdf(workspaceId)
  const bulkPatch = useBulkPatchSearchHits(workspaceId)
  const snowball = useSnowball(workspaceId)
  const newHits = useNewHitsAvailable(run)
  const refreshHits = useRefreshHits(workspaceId)
  const parentRef = useRef<HTMLDivElement>(null)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [filterText, setFilterText] = useState('')
  const [previewWidth, setPreviewWidth] = useState(() => loadPanelWidth(HIT_PREVIEW, browserStorage()))
  useEffect(() => savePanelWidth(HIT_PREVIEW, browserStorage(), previewWidth), [previewWidth])
  useEffect(() => saveHitSort(browserStorage(), workspaceId, sort), [workspaceId, sort])
  const ranked = useRankedHits(workspaceId, sort === 'ranked', inbox)

  const rows = sort === 'ranked' ? (ranked.data?.items ?? []) : (data?.pages.flatMap((page) => page.items) ?? [])
  const rawFound = totalRawFound(run)
  const filter = filterText.trim().toLowerCase()
  const filtered = filter !== '' || (sort !== 'ranked' && minRelevance != null)
  const filteredRows = filter ? rows.filter((hit) => matchesFilter(hit, filter)) : rows
  const visibleRows = sortVisibleRows(sort, filteredRows)
  // Falls back to the first loaded row, so the panel is never empty on first paint (mirrors PaperList) — and to
  // whichever row is first once a filter drops the previously selected one out of view.
  // What the import button imports: the server (import_hits with no ids) takes every not-yet-imported hit marked
  // relevant in the whole workspace, whatever the filter, so count that from the plain, unfiltered pool query (same
  // cache key as the default view, no extra request). 'failed' hits are retried by the backend, so they count.
  const pool = useSearchHits(workspaceId)
  const morePages = pool.hasNextPage
  const importable = (pool.data?.pages.flatMap((page) => page.items) ?? []).filter(
    (hit) => hit.stage1_status === 'relevant' && hit.acquisition_status !== 'imported' && hit.acquisition_status !== 'manual',
  ).length
  const poolUnsettled = pool.isPending || pool.isError
  const importLabel = morePages || poolUnsettled ? 'Import all relevant results' : `Import ${importable} relevant result${importable === 1 ? '' : 's'}`
  const importDisabled = poolUnsettled || (!morePages && importable === 0)
  const previewed = visibleRows.find((hit) => hit.id === previewId) ?? visibleRows[0]
  const {
    checkedIds,
    bulkReason,
    setBulkReason,
    allVisibleChecked,
    someVisibleChecked,
    toggleChecked,
    toggleCheckAllVisible,
    bulkMark,
    bulkAccept,
    bulkMarkNotRelevant,
    clearChecked,
  } = useHitSelection(visibleRows, bulkPatch, acceptSuggestions)

  const { narrow, virtualizer, virtualItems, onListKeyDown } = useHitList({
    visibleRows,
    sort,
    previewedId: previewed?.id,
    setPreviewId,
    parentRef,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    newHits,
    refreshHits,
  })
  const onReview = (hitId: string, body: HitReviewUpdate) => reviewHit.mutate({ hitId, body })
  // Seeds a snowball hop straight from this hit — no import required first (see HitMenu's onSnowball docstring).
  const onSnowball = (hitId: string) => snowball.mutate({ seed_hit_ids: [hitId], backward: true, forward: true })

  const statusMessage = hitStatusMessage({ acceptSuggestions, bulkPatch, importHits, importAllHits, clearHits, reviewHit, uploadHitPdf, snowball })

  const listLoading = sort === 'ranked' ? ranked.isPending : isPending
  const listState = listLoading ? (
    <TabSkeleton label="Loading search results" />
  ) : (
    !(sort === 'ranked' ? ranked.isError : isError) &&
    visibleRows.length === 0 && (
      <EmptyState
        title={filtered ? 'No results match these filters.' : inbox ? 'Nothing new from this search since you last looked.' : 'No results yet: run a search above.'}
        action={
          filtered && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setFilterText('')
                setMinRelevance(null)
              }}
            >
              Clear filters
            </Button>
          )
        }
      />
    )
  )

  return (
    <div className="flex min-h-[24rem] flex-1 flex-col">
      <HitToolbar
        allVisibleChecked={allVisibleChecked}
        someVisibleChecked={someVisibleChecked}
        onToggleCheckAll={toggleCheckAllVisible}
        visibleCount={visibleRows.length}
        totalCount={rows.length}
        filter={filter}
        filterText={filterText}
        onFilterTextChange={setFilterText}
        onFilterKeyDown={onListKeyDown}
        rawFound={rawFound}
        listLoading={listLoading}
        importLabel={importLabel}
        importDisabled={importDisabled}
        poolUnsettled={poolUnsettled}
        importPending={importAllHits.isPending}
        onImport={() => importAllHits.mutate()}
        clearPending={clearHits.isPending}
        onClearOld={() => clearHits.mutate()}
      />
      {checkedIds.size > 0 && (
        <HitBulkBar
          count={checkedIds.size}
          bulkPending={bulkPatch.isPending}
          acceptPending={acceptSuggestions.isPending}
          bulkReason={bulkReason}
          onBulkReasonChange={setBulkReason}
          onMark={bulkMark}
          onAccept={bulkAccept}
          onMarkNotRelevant={bulkMarkNotRelevant}
          onClear={clearChecked}
        />
      )}
      {inbox && (
        <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5 text-sm">
          <span className="min-w-0 flex-1 truncate">
            New from “{inbox.query}” since {new Date(inbox.since).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
          </span>
          <Button type="button" size="sm" variant="ghost" onClick={onLeaveInbox}>Show all results</Button>
        </div>
      )}
      <RankSortBar
        sort={sort}
        onSortChange={setSort}
        ranked={ranked.data}
        minRelevance={minRelevance}
        onMinRelevanceChange={setMinRelevance}
      />
      {/* One status line, not one paragraph per mutation: with up to 9 independent isError/isSuccess flags on
          this screen, stacking them all would both clutter the view and shift the hit list up/down as each one
          comes and goes. Errors win over a success notice, in roughly the order a reader would expect to act on
          them (bulk/global actions before single-row ones). */}
      {statusMessage && (
        <p
          role={statusMessage.tone === 'error' ? 'alert' : 'status'}
          className={cn('px-3 py-1 text-xs', statusMessage.tone === 'error' ? 'text-destructive' : 'text-muted-foreground')}
        >
          {statusMessage.text}
        </p>
      )}
      {(sort === 'ranked' ? ranked.isError : isError) && (
        <LoadError
          message={(sort === 'ranked' ? ranked.error : error)?.message ?? 'Could not load results.'}
          onRetry={() => void (sort === 'ranked' ? ranked.refetch() : refetch())}
        />
      )}
      <div
        className={cn(
          'grid flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_var(--preview-track)]',
          visibleRows.length > 0 && 'min-h-[16rem]',
        )}
        style={{ '--preview-track': panelTrack(HIT_PREVIEW, previewWidth) } as CSSProperties}
      >
        <div
          ref={parentRef}
          aria-label="Result list"
          tabIndex={0}
          onKeyDown={onListKeyDown}
          className="min-h-0 overflow-auto outline-none"
        >
          {listState}
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {virtualItems.map((virtualRow) => {
              const hit = visibleRows[virtualRow.index]
              return (
                <HitRow
                  key={hit.id}
                  hit={hit}
                  index={virtualRow.index}
                  start={virtualRow.start}
                  size={virtualRow.size}
                  narrow={narrow}
                  selected={hit.id === previewed?.id}
                  checked={checkedIds.has(hit.id)}
                  measureRef={narrow ? virtualizer.measureElement : undefined}
                  acceptPending={acceptSuggestions.isPending}
                  onToggleChecked={toggleChecked}
                  onSelect={setPreviewId}
                  onAccept={(hitId) => acceptSuggestions.mutate([hitId])}
                  onReview={onReview}
                  onSnowball={onSnowball}
                />
              )
            })}
          </div>
        </div>
        {/* Desktop only: the preview panel follows the click/arrow-key selection, which a touch screen doesn't
            have arrow keys for anyway — same split as PaperPreview. */}
        {previewed && (
          <div className="relative hidden min-h-0 min-w-0 lg:block">
            <PanelResizeHandle
              limits={HIT_PREVIEW}
              width={previewWidth}
              onWidthChange={setPreviewWidth}
              label="Resize preview"
              inset={PANE_PADDING_PX}
            />
            <HitPreview
              hit={previewed}
              workspaceId={workspaceId}
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
