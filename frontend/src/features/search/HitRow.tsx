import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import type { Hit, HitReviewUpdate } from '@/entities'
import { HitContextMenu, HitMenu } from '@/features/search/HitMenu'
import { sourceLabel, statusLabel } from '@/features/search/hitReview'
import { ROW_HEIGHT_NARROW } from '@/features/search/hitTableLayout'
import { StatusDot } from '@/features/search/StatusDot'
import { SuggestionChip } from '@/features/search/SuggestionChip'

/** One positioned row of the virtualized hit list. */
export function HitRow({
  hit,
  index,
  start,
  size,
  narrow,
  selected,
  checked,
  measureRef,
  acceptPending,
  onToggleChecked,
  onSelect,
  onAccept,
  onReview,
  onSnowball,
}: {
  hit: Hit
  index: number
  start: number
  size: number
  narrow: boolean
  selected: boolean
  checked: boolean
  measureRef?: (element: Element | null) => void
  acceptPending: boolean
  onToggleChecked: (hitId: string) => void
  onSelect: (hitId: string) => void
  onAccept: (hitId: string) => void
  onReview: (hitId: string, body: HitReviewUpdate) => void
  onSnowball: (hitId: string) => void
}) {
  const byline = [hit.authors?.slice(0, 3).join(', '), hit.year].filter(Boolean).join(' · ')
  return (
    <HitContextMenu hit={hit} onReview={onReview} onSnowball={onSnowball}>
      <div
        className={cn(
          'flex w-full cursor-pointer items-center gap-2 border-b px-3 text-sm hover:bg-muted',
          narrow && 'flex-wrap content-center gap-y-1 py-1.5',
          selected && 'bg-muted',
        )}
        // Narrow rows are measured: a row whose suggestion chips need a third line grows instead of
        // spilling over the next one. Desktop rows keep their fixed single line.
        ref={measureRef}
        data-index={narrow ? index : undefined}
        style={{
          position: 'absolute', top: start, width: '100%',
          ...(narrow ? { minHeight: ROW_HEIGHT_NARROW } : { height: size }),
        }}  // fmt: skip
        aria-selected={selected}
        onClick={() => onSelect(hit.id)}
        onFocus={() => onSelect(hit.id)}
      >
        <Checkbox
          aria-label={`Select ${hit.title ?? hit.normalized_title}`}
          checked={checked}
          onCheckedChange={() => onToggleChecked(hit.id)}
          onClick={(event) => event.stopPropagation()}
          className="shrink-0"
        />
        <span className={cn('flex-1 truncate', narrow && 'basis-[calc(100%-2rem)]')}>
          {hit.title ?? hit.normalized_title}
          {byline && <span className="text-muted-foreground"> · {byline}</span>}
        </span>
        {hit.sources[0] && (
          <span className="shrink-0 rounded-full border px-1.5 py-0.5 text-xs text-muted-foreground">
            {sourceLabel(hit.sources[0])}
          </span>
        )}
        <SuggestionChip hit={hit} />
        {(hit.suggestion === 'include' || hit.suggestion === 'exclude') && !hit.stage1_status && (
          <Button
            type="button"
            size="xs"
            variant="outline"
            aria-label={`Accept AI suggestion: ${hit.title ?? hit.normalized_title}`}
            disabled={acceptPending}
            onClick={(event) => {
              event.stopPropagation()
              onAccept(hit.id)
            }}
          >
            Accept
          </Button>
        )}
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <StatusDot status={hit.stage1_status} />
          {statusLabel(hit.stage1_status)}
        </span>
        <HitMenu hit={hit} onReview={onReview} onSnowball={onSnowball} />
      </div>
    </HitContextMenu>
  )
}
