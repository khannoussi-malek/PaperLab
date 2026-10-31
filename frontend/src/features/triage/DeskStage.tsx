import { useCallback, useEffect, useRef, useState } from 'react'
import type { Paper } from '@/api/client'
import { cn } from '@/lib/utils'
import type { DeskLayout } from './layout'
import { PILES, type Pile } from './piles'
import { Targets } from './Targets'
import { TriageCard } from './TriageCard'
import { useCardDrag } from './useCardDrag'

export const DEPARTURE_MS = 220

const OUT: Record<string, string> = {
  right: 'translate(640px, 30px) rotate(24deg)',
  left: 'translate(-640px, 30px) rotate(-24deg)',
  up: 'translate(0, -520px) rotate(6deg)',
  down: 'translate(0, 520px) rotate(-6deg)',
}

type Departing = { pile: Pile; paper?: Paper }
type Props = {
  top: Paper
  behind: Paper[]
  counts: Record<Pile, number>
  layout: DeskLayout
  /** The pile whose key is held: its target and stamp show. */
  hot: Pile | null
  /** The card held over Not relevant while a reason is picked. */
  hovering: Pile | null
  /** A new object each time a card leaves: it flies out for DEPARTURE_MS while the next card is already live. */
  departing: Departing | null
  onCommit: (pile: Pile) => void
  onHover: (pile: Pile | null) => void
  reduced: boolean
  /** The conclusion's Show in PDF: passed only when the paper has a PDF. */
  onShowInPdf?: (page: number) => void
}

const PAPER = 'paper-surface border-[#e6dfcc]'
const DOTS =
  'bg-muted bg-[radial-gradient(circle_at_1px_1px,color-mix(in_srgb,var(--muted-foreground)_22%,transparent)_1px,transparent_0)] bg-[length:18px_18px]'

function Clone({ item, onDone }: { item: Departing & { id: number }; onDone: (id: number) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const dir = PILES[item.pile].target
    // ponytail: jsdom and old browsers lack element.animate; the clone then just sits out its 220 ms
    ref.current?.animate?.(
      [{ transform: 'none', opacity: 1 }, { transform: dir ? OUT[dir] : 'translateY(-40px)', opacity: 0 }],
      { duration: DEPARTURE_MS, easing: 'ease-out', fill: 'forwards' },
    )
    // each clone owns its removal: later departures, resets or a reduced flip never cancel it
    const t = setTimeout(() => onDone(item.id), DEPARTURE_MS)
    return () => clearTimeout(t)
  }, [item.pile, item.id, onDone])
  return (
    <div
      ref={ref}
      data-triage-departing={item.pile}
      aria-hidden="true"
      inert
      className={cn('paper-surface pointer-events-none absolute inset-x-0 top-0 z-30 rounded-xl border border-[#e6dfcc] p-6 font-heading text-xl font-semibold shadow-xl')}
    >
      {item.paper?.title}
    </div>
  )
}

/** The desk: a dotted surface, the card on top of its stack, four glass targets and the drag that picks one. */
export function DeskStage({ top, behind, counts, layout, hot, hovering, departing, onCommit, onHover, reduced, onShowInPdf }: Props) {
  const cardRef = useRef<HTMLDivElement>(null)
  const [dragPile, setDragPile] = useState<Pile | null>(null)
  const [clones, setClones] = useState<(Departing & { id: number })[]>([])
  const seq = useRef(0)
  const single = layout === 'single'

  const handled = useRef<Departing | null>(null)
  useEffect(() => {
    if (!departing || reduced || handled.current === departing) return
    handled.current = departing // StrictMode runs effects twice: one departure, one clone
    setClones((c) => [...c, { ...departing, id: ++seq.current }])
  }, [departing, reduced])
  const drop = useCallback((id: number) => setClones((c) => c.filter((x) => x.id !== id)), [])

  useCardDrag(cardRef, {
    enabled: !single,
    reduced,
    onProgress: (_dx, _dy, pile) => { setDragPile(pile); onHover(pile) },
    onCommit: (pile) => { setDragPile(null); onHover(null); onCommit(pile) },
    onCancel: () => { setDragPile(null); onHover(null) },
  })

  const stamped = dragPile ?? hot
  const active = dragPile ?? hot ?? hovering
  return (
    <div
      data-desk-stage
      data-layout={layout}
      className={cn(
        'relative isolate overflow-hidden rounded-2xl border border-border',
        !single && DOTS,
        layout === 'wide' && 'min-h-[480px] px-40 py-20',
        layout === 'tabs' && 'min-h-[480px] px-6 py-16',
      )}
    >
      {!single && <Targets counts={counts} layout={layout === 'wide' ? 'wide' : 'tabs'} active={active} onCommit={onCommit} />}
      <div className="relative mx-auto max-w-xl">
        {!single && !reduced && behind.slice(0, 2).map((p, i) => (
          <div
            key={p.id}
            data-triage-edge
            aria-hidden="true"
            className={cn('pointer-events-none absolute inset-0 -z-10 rounded-xl border shadow-md', PAPER)}
            style={{ transform: `translateY(${(i + 1) * 8}px) scale(${1 - (i + 1) * 0.04})` }}
          />
        ))}
        <div
          ref={cardRef}
          className={cn(
            'relative z-10 rounded-xl',
            !single && 'cursor-grab touch-none active:cursor-grabbing',
            hovering === 'not_relevant' && !reduced && '-translate-x-6 -rotate-3 motion-safe:transition-transform',
          )}
        >
          <TriageCard paper={top} onShowInPdf={onShowInPdf} />
          {stamped && (
            <span
              data-triage-stamp
              aria-hidden="true"
              className={cn(
                'pointer-events-none absolute right-4 top-4 rounded-md border-2 border-primary bg-paper px-2.5 py-0.5 text-xs font-bold uppercase tracking-wider text-primary',
                !reduced && 'rotate-[8deg] motion-safe:animate-in motion-safe:fade-in motion-safe:duration-150',
              )}
            >
              {PILES[stamped].label}
            </span>
          )}
        </div>
        {clones.map((c) => <Clone key={c.id} item={c} onDone={drop} />)}
      </div>
    </div>
  )
}
