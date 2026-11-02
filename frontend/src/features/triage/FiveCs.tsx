import { ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { FIVE_CS } from './piles'

type Props = {
  open: boolean
  /** Bit i is FIVE_CS[i]; null until the group is first opened. */
  mask: number | null
  onToggle: () => void
  onTick: (n: number) => void
  /** The single column: no key hints, taller lines. */
  single: boolean
}

/** "First pass: five Cs" on the card: plain checkboxes, collapsed by default, never a gate. */
export function FiveCs({ open, mask, onToggle, onTick, single }: Props) {
  const on = (i: number) => ((mask ?? 0) & (1 << i)) !== 0
  const ticked = FIVE_CS.filter((_, i) => on(i)).length
  return (
    <div role="group" aria-label="First pass: five Cs" className="space-y-1">
      <Button type="button" variant="ghost" size="sm" className={cn('-ml-2', single && 'min-h-11')} aria-expanded={open} onClick={onToggle}>
        <ChevronRight aria-hidden className={cn('motion-safe:transition-transform', open && 'rotate-90')} />
        First pass: five Cs
        {ticked > 0 && <span className="tabular-nums text-muted-foreground">({ticked} of {FIVE_CS.length})</span>}
        {!single && <kbd aria-hidden className="rounded border border-border px-1 text-xs text-muted-foreground">C</kbd>}
      </Button>
      {open && (
        <ul className="space-y-1 text-sm">
          {FIVE_CS.map((text, i) => (
            <li key={text}>
              {/* a mouse press leaves focus on the desk, so the desk's keys keep working; Tab still reaches each box */}
              <label className={cn('flex cursor-pointer items-start gap-2', single && 'min-h-11 items-center')} onMouseDown={(e) => e.preventDefault()}>
                <Checkbox className="mt-0.5" checked={on(i)} onCheckedChange={() => onTick(i + 1)} />
                {!single && <kbd aria-hidden className="rounded border border-border px-1 text-xs text-muted-foreground">{i + 1}</kbd>}
                <span>{text}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
