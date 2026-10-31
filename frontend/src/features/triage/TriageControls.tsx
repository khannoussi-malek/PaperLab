import { Undo2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Alert } from './useTriageSession'
import type { DeskLayout } from './layout'
import { PILES, type Pile } from './piles'

const BUTTONS: Pile[] = ['read_closely', 'skim', 'later', 'not_relevant', 'skip']
const hint = (p: Pile) => (p === 'skip' ? 'Space' : String(PILES[p].key))

type Undo = { label: string; count: number }

export function UndoButton({ undo, onUndo }: { undo: Undo | null; onUndo: () => void }) {
  return (
    <Button type="button" variant="ghost" size="sm" disabled={!undo} onClick={onUndo}>
      <Undo2 aria-hidden />
      {undo ? <>Undo: {undo.label} <span className="tabular-nums text-muted-foreground">({undo.count})</span></> : 'Nothing to undo'}
    </Button>
  )
}

type Props = {
  layout: DeskLayout
  undo: Undo | null
  onUndo: () => void
  onDecide: (pile: Pile) => void
  progress: { decided: number; skipped: number; total: number }
}

/** Undo, the five decision buttons (key hints off in the single column) and the session's progress. */
export function TriageControls({ layout, undo, onUndo, onDecide, progress }: Props) {
  const single = layout === 'single'
  const { decided, skipped, total } = progress
  return (
    <div data-triage-region tabIndex={-1} className="flex flex-col gap-3 outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
      <div className="flex flex-wrap items-center gap-3">
        <UndoButton undo={undo} onUndo={onUndo} />
        <div className="ml-auto flex min-w-48 flex-1 flex-col gap-1 sm:max-w-sm">
          <div
            role="progressbar"
            aria-label="Triage progress"
            aria-valuemin={0}
            aria-valuenow={decided}
            aria-valuemax={total}
            className="h-1.5 overflow-hidden rounded-full bg-muted"
          >
            <div className="h-full origin-left bg-primary" style={{ width: `${total ? (decided / total) * 100 : 0}%` }} />
          </div>
          <p className="text-xs text-muted-foreground">
            {decided} of {total} decided this session{skipped > 0 && ` · ${skipped} skipped`}
          </p>
        </div>
      </div>
      <div role="group" aria-label="Decide" className={cn('flex gap-2', single ? 'flex-col' : 'flex-wrap')}>
        {BUTTONS.map((p) => (
          <Button
            key={p}
            type="button"
            variant={p === 'skip' ? 'ghost' : 'secondary'}
            className={cn(single && 'min-h-11 justify-start')}
            onClick={() => onDecide(p)}
          >
            {PILES[p].label}
            {!single && <kbd className="rounded border border-border px-1 text-xs text-muted-foreground">{hint(p)}</kbd>}
          </Button>
        ))}
      </div>
    </div>
  )
}

/** Always mounted: the polite live region for each outcome and the failure strip. */
export function DeskStatus({ announcement, alert }: { announcement: string; alert: Alert | null }) {
  return (
    <>
      <div aria-live="polite" role="status" className="sr-only">{announcement}</div>
      {alert && (
        <div role="alert" className="flex items-center gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm">
          <span>{alert.message}</span>
          {alert.retry && <Button type="button" size="sm" variant="outline" onClick={alert.retry}>Retry</Button>}
        </div>
      )}
    </>
  )
}
