import { useEffect, useState, type FormEvent } from 'react'
import { api, type NumberCandidate } from '@/api/client'
import { useDatasetMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { pressable } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { SelectionAnchor } from '../reader/selection'

type Props = {
  paperId: string
  anchor: SelectionAnchor
  onClose: () => void
}

/** A candidate number chip, like the Notes filter chips but `role="radio"` for the one chosen candidate. */
function CandidateChip({ candidate, chosen, onChoose }: { candidate: NumberCandidate; chosen: boolean; onChoose: () => void }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={chosen}
      onClick={onChoose}
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium tabular-nums ring-1 transition-[color,background-color,box-shadow,scale] duration-150 outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
        pressable,
        chosen ? 'bg-secondary text-foreground ring-input' : 'text-muted-foreground ring-border ring-inset hover:bg-muted hover:text-foreground',
      )}
    >
      {candidate.raw}
    </button>
  )
}

/** Opens on a text selection with the numbers found in it, and saves the chosen one as a row in the paper's numbers dataset. */
export function AddNumberDialog({ paperId, anchor, onClose }: Props) {
  const { addNumber } = useDatasetMutations()
  const [candidates, setCandidates] = useState<NumberCandidate[] | null>(null)
  const [candidatesError, setCandidatesError] = useState<string | null>(null)
  const [chosen, setChosen] = useState(0)
  const [label, setLabel] = useState('')
  const [value, setValue] = useState('')
  const [error, setError] = useState('')
  const [unit, setUnit] = useState('')

  useEffect(() => {
    let active = true
    api.numberCandidates(anchor.quotedText).then(
      (found) => {
        if (!active) return
        setCandidates(found)
        const first = found[0]
        if (first) {
          setValue(String(first.value))
          setError(first.error !== null ? String(first.error) : '')
          setUnit(first.unit_hint ?? '')
        }
      },
      (e: Error) => active && setCandidatesError(e.message),
    )
    return () => {
      active = false
    }
  }, [anchor.quotedText])

  function choose(index: number, candidate: NumberCandidate) {
    setChosen(index)
    setValue(String(candidate.value))
    setError(candidate.error !== null ? String(candidate.error) : '')
    setUnit(candidate.unit_hint ?? '')
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    const raw = error ? `${value} ± ${error}` : value
    try {
      await addNumber.mutateAsync({ paperId, number: { label, raw, unit, page: anchor.page, bbox: anchor.rects } })
      onClose()
    } catch {
      // shown in the alert below from addNumber.error
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border')}>
        <form onSubmit={save} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Add as number</DialogTitle>
            <DialogDescription>Save a number from the selected text to this paper's numbers dataset.</DialogDescription>
          </DialogHeader>

          {candidatesError && (
            <Alert variant="destructive">
              <AlertDescription>{candidatesError}</AlertDescription>
            </Alert>
          )}
          {candidates?.length === 0 && <p className="text-sm text-muted-foreground">No number found in the selection.</p>}
          {candidates && candidates.length > 0 && (
            <div role="radiogroup" aria-label="Number found" className="flex flex-wrap gap-2">
              {candidates.map((candidate, i) => (
                <CandidateChip key={i} candidate={candidate} chosen={i === chosen} onChoose={() => choose(i, candidate)} />
              ))}
            </div>
          )}

          <div className="grid gap-1.5">
            <Label htmlFor="number-label">Label</Label>
            <Input id="number-label" autoFocus required maxLength={200} value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="number-value">Value</Label>
              <Input id="number-value" className="tabular-nums" value={value} onChange={(e) => setValue(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="number-error">± error</Label>
              <Input id="number-error" className="tabular-nums" value={error} onChange={(e) => setError(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="number-unit">Unit</Label>
              <Input id="number-unit" value={unit} onChange={(e) => setUnit(e.target.value)} />
            </div>
          </div>

          {addNumber.error && (
            <Alert variant="destructive">
              <AlertDescription>{addNumber.error.message}</AlertDescription>
            </Alert>
          )}

          <DialogFooter className="bg-transparent">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={label.trim() === '' || value.trim() === '' || addNumber.isPending}>
              {addNumber.isPending ? 'Adding…' : 'Add number'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
