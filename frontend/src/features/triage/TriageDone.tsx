import { useTriageSummary } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { UndoButton } from './TriageControls'
import { PILES, PILE_ORDER } from './piles'

type Props = {
  sessionId: string
  skipped: number
  /** False while a write is pending: the skipped cards' state isn't settled yet. */
  canReviewSkipped: boolean
  newSince: number
  undo: { label: string; count: number } | null
  onUndo: () => void
  onReviewSkipped: () => void
  onShowKept: () => void
  onAddNew: () => void
  onStartOver: () => void
  onBack: () => void
}

const minutes = (ms: number) => (ms < 60_000 ? 'under a minute' : `about ${Math.round(ms / 60_000)} min`)

/** The end of the stack: what the session did, as plain facts, and the ways on. */
export function TriageDone({ sessionId, skipped, canReviewSkipped, newSince, undo, onUndo, onReviewSkipped, onShowKept, onAddNew, onStartOver, onBack }: Props) {
  const { data } = useTriageSummary(sessionId, true)
  return (
    <div className="grid gap-4 rounded-xl border border-glass-border bg-glass px-6 py-8">
      <h2 className="font-heading text-xl font-semibold">That is the whole stack.</h2>
      {data && (
        <ul className="grid gap-1 text-sm">
          {PILE_ORDER.filter((p) => p !== 'skip' && (data.per_pile[p] ?? 0) > 0).map((p) => (
            <li key={p}>{data.per_pile[p]} {PILES[p].label}</li>
          ))}
          {skipped > 0 && <li>{skipped} skipped</li>}
          <li>{minutes(data.card_ms)}</li>
          <li>PDF opened for {data.pdf_opened} of {data.decided}</li>
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {skipped > 0 && <Button disabled={!canReviewSkipped} onClick={onReviewSkipped}>Review the skipped ({skipped})</Button>}
        <Button variant="secondary" onClick={onShowKept}>Show kept papers in the list</Button>
        {newSince > 0 && <Button variant="secondary" onClick={onAddNew}>Add {newSince} new {newSince === 1 ? 'paper' : 'papers'}</Button>}
        <Button variant="secondary" onClick={onStartOver}>Start over</Button>
        <Button variant="outline" onClick={onBack}>Back to the list</Button>
        <UndoButton undo={undo} onUndo={onUndo} />
      </div>
    </div>
  )
}
