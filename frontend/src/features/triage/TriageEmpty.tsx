import { Button } from '@/components/ui/button'

/** The desk opened on a view where every paper already has a decision (or none can be shown yet). */
export function TriageEmpty({ canInclude, onInclude, onBack }: { canInclude: boolean; onInclude: () => void; onBack: () => void }) {
  return (
    <div className="grid place-items-center gap-3 rounded-xl border border-dashed border-glass-border px-6 py-12 text-center">
      <p className="text-muted-foreground">Nothing to triage here. Every paper in this view already has a decision.</p>
      <div className="flex gap-2">
        {canInclude && <Button variant="secondary" onClick={onInclude}>Include decided papers</Button>}
        <Button variant="outline" onClick={onBack}>Back to the list</Button>
      </div>
    </div>
  )
}
