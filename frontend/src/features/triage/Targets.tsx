import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PILES, type Pile } from './piles'

type TargetPile = Exclude<Pile, 'skip'>
const TARGETS: { pile: TargetPile; Icon: LucideIcon; wide: string; tabs: string }[] = [
  { pile: 'read_closely', Icon: ArrowRight, wide: 'right-4 top-1/2 -translate-y-1/2', tabs: 'right-3 top-3' },
  { pile: 'skim', Icon: ArrowDown, wide: 'bottom-4 left-1/2 -translate-x-1/2', tabs: 'right-3 bottom-3' },
  { pile: 'later', Icon: ArrowUp, wide: 'top-4 left-1/2 -translate-x-1/2', tabs: 'left-3 top-3' },
  { pile: 'not_relevant', Icon: ArrowLeft, wide: 'left-4 top-1/2 -translate-y-1/2', tabs: 'left-3 bottom-3' },
]

type Props = {
  counts: Record<Pile, number>
  layout: 'wide' | 'tabs'
  active: Pile | null
  onCommit: (pile: Pile) => void
}

/** Four glass chips: icon, the pile's word and its count. The active one is `primary`-ringed. */
export function Targets({ counts, layout, active, onCommit }: Props) {
  return (
    <>
      {TARGETS.map(({ pile, Icon, wide, tabs }) => {
        const { label, key } = PILES[pile]
        const on = active === pile
        return (
          <button
            key={pile}
            type="button"
            data-triage-target={pile}
            data-active={on || undefined}
            aria-label={`${label}, key ${key}`}
            onClick={() => onCommit(pile)}
            className={cn(
              'absolute z-20 flex items-center gap-2 rounded-xl border border-glass-border bg-glass-strong px-3 py-2 text-sm outline-none',
              'motion-safe:transition-[transform,box-shadow,border-color] motion-safe:duration-200 focus-visible:ring-3 focus-visible:ring-ring/50',
              layout === 'wide' ? wide : tabs,
              on && 'border-primary text-primary ring-3 ring-primary/25',
            )}
          >
            <Icon aria-hidden className="size-4" />
            <span>{label}</span>
            <b className="min-w-4 text-right tabular-nums">{counts[pile]}</b>
          </button>
        )
      })}
    </>
  )
}
