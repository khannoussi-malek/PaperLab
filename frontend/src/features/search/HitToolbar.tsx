import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Term } from '@/components/Term'
import { NO_IMPORT_REASON } from '@/features/search/hitTableLayout'

/** The header bar above the hit list: select-all, the filter box, the counts, and the import/clear actions. */
export function HitToolbar({
  allVisibleChecked,
  someVisibleChecked,
  onToggleCheckAll,
  visibleCount,
  totalCount,
  filter,
  filterText,
  onFilterTextChange,
  onFilterKeyDown,
  rawFound,
  listLoading,
  importLabel,
  importDisabled,
  poolUnsettled,
  importPending,
  onImport,
  clearPending,
  onClearOld,
}: {
  allVisibleChecked: boolean
  someVisibleChecked: boolean
  onToggleCheckAll: () => void
  visibleCount: number
  totalCount: number
  filter: string
  filterText: string
  onFilterTextChange: (text: string) => void
  onFilterKeyDown: (event: React.KeyboardEvent) => void
  rawFound?: number
  listLoading: boolean
  importLabel: string
  importDisabled: boolean
  poolUnsettled: boolean
  importPending: boolean
  onImport: () => void
  clearPending: boolean
  onClearOld: () => void
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2 text-sm">
      <Checkbox
        aria-label="Select all visible results"
        checked={someVisibleChecked && !allVisibleChecked ? 'indeterminate' : allVisibleChecked}
        onCheckedChange={onToggleCheckAll}
        disabled={visibleCount === 0}
        className="shrink-0"
      />
      <label className="flex flex-1 items-center gap-2">
        <span className="sr-only">Search results</span>
        <input
          type="text"
          value={filterText}
          onChange={(event) => onFilterTextChange(event.target.value)}
          onKeyDown={onFilterKeyDown}
          placeholder="Search by title or abstract…"
          aria-label="Search results"
          className="h-8 w-full max-w-xs rounded-lg border bg-background px-2 text-sm"
        />
      </label>
      <span className="text-muted-foreground">
        {rawFound !== undefined && `${rawFound} found so far · `}
        {listLoading ? (
          'Loading results…' // not "0 results": a big ranked pool takes seconds
        ) : (
          <>
            {filter ? `${visibleCount} of ${totalCount}` : totalCount} <Term term="results">results</Term>{' '}
            (after filters)
          </>
        )}{' '}
        <Term term="identified">How this differs from PRISMA</Term>
      </span>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={importDisabled || importPending}
        title={importDisabled && !poolUnsettled ? NO_IMPORT_REASON : undefined}
        aria-describedby={importDisabled && !poolUnsettled ? 'import-none-reason' : undefined}
        onClick={onImport}
      >
        {importLabel}
      </Button>
      {importDisabled && !poolUnsettled && (
        <span id="import-none-reason" className="sr-only">
          {NO_IMPORT_REASON}
        </span>
      )}
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={clearPending}
        onClick={() => {
          if (window.confirm('Clear every result not yet imported? Papers already in your corpus stay untouched.')) {
            onClearOld()
          }
        }}
      >
        Clear old results
      </Button>
    </div>
  )
}
