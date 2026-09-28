import { BookMarked, BookOpenCheck } from 'lucide-react'
import { useState } from 'react'
import type { Paper } from '@/api/client'
import { useSetReading } from '@/api/queries'
import { glass } from '@/components/glass'
import { popIn } from '@/components/motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ErrorAlert } from '@/features/library/ErrorAlert'
import { cn } from '@/lib/utils'
import { LEVELS, nextPass, readingChip, TRIAGES, UNDECIDED_LABEL, type Triage } from './passes'

type Props = {
  paper: Paper
  /** Closes the popover and shows the References tab (D78 fetches on open). */
  onOpenReferences: () => void
}

/** The reader's own record of a paper (D118, D167): a toolbar popover with the passes finished, the decision, and
 * the next pass's guide. Only the reader's own clicks set either field. */
export function ReadingControl({ paper, onOpenReferences }: Props) {
  // Controlled so "Open References" can close the popover itself (Radix doesn't close a Popover on an ordinary
  // button click inside its content) before switching tabs, matching this component's own contract above.
  const [open, setOpen] = useState(false)
  const setReading = useSetReading()
  const pending = setReading.isPending ? setReading.variables.changes : null
  // ReadingIn's reading_pass is typed number | null | undefined (schema allows an absent/cleared field in
  // general), but `set()` below only ever sends a literal number for it — the ?? never fires at runtime, it just
  // satisfies nextPass's number parameter.
  const level = (pending && 'reading_pass' in pending ? pending.reading_pass : paper.reading_pass) ?? paper.reading_pass
  const triage = pending && 'triage' in pending ? pending.triage : paper.triage
  const chip = readingChip(paper.reading_pass, paper.triage)
  const guide = nextPass(level)

  function set(changes: { reading_pass: number } | { triage: Triage | null }) {
    setReading.mutate({ paperId: paper.id, changes })
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" aria-label={chip ? `Reading ${chip}` : 'Reading'}>
          <BookOpenCheck aria-hidden />
          Reading
          {chip && (
            <Badge variant="secondary" className="reading-chip font-normal">
              {chip}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className={cn(
          glass,
          popIn,
          'reading-popover w-96 origin-top-right bg-glass-strong p-4 ring-glass-border',
          'max-h-[var(--radix-popover-content-available-height)] overflow-y-auto'
        )}
      >
        <h2 id="reading-heading" className="font-heading text-lg font-semibold">
          Reading
        </h2>
        <div aria-labelledby="reading-heading" className="mt-3 grid grid-cols-2 gap-4">
          <div>
            <p id="reading-passes-label" className="text-sm font-medium">
              Passes finished
            </p>
            <RadioGroup
              aria-labelledby="reading-passes-label"
              aria-busy={pending !== null && 'reading_pass' in pending}
              value={String(level)}
              onValueChange={(value) => set({ reading_pass: Number(value) })}
              className="mt-1.5 gap-1.5"
            >
              {LEVELS.map((option) => (
                <div key={option.value} className="flex items-center gap-2">
                  <RadioGroupItem value={String(option.value)} id={`pass-${option.value}`} />
                  <Label htmlFor={`pass-${option.value}`} className="text-sm font-normal">
                    {option.label}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </div>
          <div>
            <p id="reading-decision-label" className="text-sm font-medium">
              Decision
            </p>
            <RadioGroup
              aria-labelledby="reading-decision-label"
              aria-busy={pending !== null && 'triage' in pending}
              value={triage ?? 'undecided'}
              onValueChange={(value) => set({ triage: value === 'undecided' ? null : (value as Triage) })}
              className="mt-1.5 gap-1.5"
            >
              {[...TRIAGES, { value: 'undecided' as const, label: UNDECIDED_LABEL, chip: UNDECIDED_LABEL }].map(
                (option) => (
                  <div key={option.value} className="flex items-center gap-2">
                    <RadioGroupItem value={option.value} id={`triage-${option.value}`} />
                    <Label htmlFor={`triage-${option.value}`} className="text-sm font-normal">
                      {option.label}
                    </Label>
                  </div>
                )
              )}
            </RadioGroup>
          </div>
        </div>
        {setReading.isError && <ErrorAlert message={setReading.error.message} />}
        <hr className="my-3 border-glass-border" />
        {guide ? (
          <section aria-label={guide.heading}>
            <h3 className="text-sm font-medium tabular-nums">{guide.heading}</h3>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm">
              {guide.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
            <p className="mt-1.5 text-sm">
              <span className="font-medium">Done when</span>
              {guide.doneWhen.slice('Done when'.length)}
            </p>
            {guide.fiveCs && (
              <>
                <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm">
                  {guide.fiveCs.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
                <p className="mt-1.5 text-sm">{guide.then}</p>
              </>
            )}
            {guide.references && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-2"
                onClick={() => {
                  setOpen(false)
                  onOpenReferences()
                }}
              >
                <BookMarked aria-hidden />
                Open References
              </Button>
            )}
          </section>
        ) : (
          <p className="text-sm">You’ve finished all three passes.</p>
        )}
        <p className="mt-3 text-xs text-muted-foreground">Only you set this. PaperLab never marks a pass for you.</p>
      </PopoverContent>
    </Popover>
  )
}
