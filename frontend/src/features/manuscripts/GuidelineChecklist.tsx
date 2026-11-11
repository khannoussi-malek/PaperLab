import { useEffect, useRef, useState } from 'react'
import type { ReportingGuideline, ReportingGuidelineItem } from '@/api/client'
import { useReportingGuidelines, useUpdateManuscript } from '@/api/queries'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

type Props = { manuscriptId: string; checklist: Record<string, unknown> }
type Ticks = Record<string, unknown>

/** Ticks are kept as `"<guideline>:<item>": true`; the chosen guideline as `guideline: "<id>"`. Suggestions only: nothing is auto-ticked. */
const itemKey = (guideline: string, item: ReportingGuidelineItem) => `${guideline}:${item.id}`
const without = (dict: Ticks, key: string): Ticks => Object.fromEntries(Object.entries(dict).filter(([k]) => k !== key))

function bySection(items: ReportingGuidelineItem[]): [string, ReportingGuidelineItem[]][] {
  const groups = new Map<string, ReportingGuidelineItem[]>()
  for (const item of items) groups.set(item.section, [...(groups.get(item.section) ?? []), item])
  return [...groups]
}

function GuidelineItems({ guideline, shown, onToggle }: { guideline: ReportingGuideline; shown: Ticks; onToggle: (key: string, on: boolean) => void }) {
  return (
    <>
      <p className="px-2 text-xs text-muted-foreground">
        {guideline.items.filter((i) => shown[itemKey(guideline.id, i)] === true).length} of {guideline.items.length} ticked
      </p>
      {bySection(guideline.items).map(([section, items]) => (
        <div key={section} className="flex flex-col gap-1 px-2">
          <h3 className="pt-1 text-xs font-medium text-muted-foreground">{section}</h3>
          <ul className="flex flex-col gap-1">
            {items.map((item) => {
              const key = itemKey(guideline.id, item)
              const id = `guideline-${key}`
              return (
                <li key={key} className="flex items-center gap-2">
                  <Checkbox id={id} checked={shown[key] === true} onCheckedChange={(v) => onToggle(key, v === true)} />
                  <Label htmlFor={id} className="text-sm font-normal">{item.text}</Label>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </>
  )
}

/** Each change is built from `latest`, the freshest ticks (the prop, or the dict last sent), so quick ticks don't drop each other. */
export function GuidelineChecklist({ manuscriptId, checklist }: Props) {
  const guidelines = useReportingGuidelines()
  const update = useUpdateManuscript()
  const [shown, setShown] = useState<Ticks>(checklist)
  const [fromProp, setFromProp] = useState(checklist)
  if (fromProp !== checklist) {
    setFromProp(checklist)
    setShown(checklist)
  }
  const latest = useRef<Ticks>(checklist)
  useEffect(() => {
    latest.current = checklist
  }, [checklist])

  const send = (next: Ticks) => {
    latest.current = next
    setShown(next)
    update.mutate({ id: manuscriptId, patch: { checklist: next } })
  }
  const toggle = (key: string, on: boolean) => send(on ? { ...latest.current, [key]: true } : without(latest.current, key))
  const pick = (id: string) => {
    const rest = without(latest.current, 'guideline')
    send(id ? { ...rest, guideline: id } : rest)
  }

  const guideline = typeof shown.guideline === 'string' ? shown.guideline : ''
  const chosen = guidelines.data?.find((g) => g.id === guideline)
  return (
    <section aria-label="Reporting checklist" className="flex flex-col gap-2">
      <h2 className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Reporting checklist</h2>
      <div className="px-2">
        <select
          aria-label="Reporting guideline"
          value={guideline}
          onChange={(e) => pick(e.target.value)}
          className="w-full rounded-md border border-input bg-transparent px-2 py-1 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        >
          <option value="">None</option>
          {(guidelines.data ?? []).map((g) => (
            <option key={g.id} value={g.id}>{g.label}</option>
          ))}
        </select>
      </div>
      {chosen && <GuidelineItems guideline={chosen} shown={shown} onToggle={toggle} />}
    </section>
  )
}
