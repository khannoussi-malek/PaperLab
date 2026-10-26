import { useUpdateManuscript } from '@/api/queries'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

export const FINAL_STEPS = ['Edit for clarity and flow', 'Check grammar and consistency', 'Format for the target venue', 'Submit'] as const

type Props = { manuscriptId: string; checklist: Record<string, unknown> }

/** Ticks are kept on the manuscript as `{ [step]: true }`. */
export function FinalStepsChecklist({ manuscriptId, checklist }: Props) {
  const update = useUpdateManuscript()
  const toggle = (step: string, on: boolean) => {
    const next = Object.fromEntries(Object.entries(checklist).filter(([k]) => k !== step))
    update.mutate({ id: manuscriptId, patch: { checklist: on ? { ...next, [step]: true } : next } })
  }
  return (
    <section aria-label="Final steps">
      <h2 className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Final steps</h2>
      <ul className="flex flex-col gap-1 px-2">
        {FINAL_STEPS.map((step) => (
          <li key={step} className="flex items-center gap-2">
            <Checkbox id={`step-${step}`} checked={checklist[step] === true} onCheckedChange={(v) => toggle(step, v === true)} />
            <Label htmlFor={`step-${step}`} className="text-sm font-normal">{step}</Label>
          </li>
        ))}
      </ul>
    </section>
  )
}
