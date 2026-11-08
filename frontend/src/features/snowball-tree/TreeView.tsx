import { useMemo, useRef, useState } from 'react'
import type { ProvenanceOut } from '@/api/client'
import { cn } from '@/lib/utils'
import { BOX_H, BOX_W, COL, tidyLayout, type Box } from './layout'
import { decisionWord, levelHeader } from './levelText'

type Props = {
  data: ProvenanceOut
  selected: string | null
  onSelect: (id: string) => void
  folded: Set<string>
  onToggleFold: (id: string) => void
  hidden?: Set<string>
}

const HEADER_H = 22
const TONE: Record<string, string> = {
  relevant: 'border-primary bg-primary/10',
  not_relevant: 'border-destructive bg-destructive/10',
  none: 'border-border bg-muted',
}
const curve = (x1: number, y1: number, x2: number, y2: number) => {
  const mid = (x1 + x2) / 2
  return `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`
}

function BoxButton({ box, selected, onSelect }: { box: Box; selected: boolean; onSelect: (id: string) => void }) {
  const { node, root } = box
  const decision = node ? (node.decision === 'relevant' || node.decision === 'not_relevant' ? node.decision : 'none') : 'root'
  const label = node ? `${node.title}, level ${node.level}, ${decisionWord(node.decision)}` : `${root!.label}, search`
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={selected}
      data-decision={decision}
      data-faded={box.faded}
      onClick={() => onSelect(box.id)}
      style={{ left: box.x, top: box.y + HEADER_H, width: BOX_W, height: BOX_H }}
      className={cn(
        'absolute flex flex-col justify-center overflow-hidden rounded-md border px-2 text-left text-xs transition-colors duration-150',
        TONE[decision] ?? 'border-border bg-card',
        box.faded && 'opacity-40',
        selected && 'ring-2 ring-ring',
      )}
    >
      {/* Task 8 puts the branch-state mark (open arrow / bar) on the right edge of this row. */}
      <span className="flex items-center gap-1">
        <span className="min-w-0 flex-1 truncate font-medium" title={node?.title ?? root!.label}>{node?.title ?? root!.label}</span>
        {node?.suggestion && <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-provenance-llm" />}
        {box.extraPaths > 0 && <span className="shrink-0 text-[10px] text-muted-foreground">+{box.extraPaths} other paths</span>}
      </span>
      {root && <span className="truncate text-[10px] text-muted-foreground">{root.hit_count.toLocaleString('en')} hits · {root.on_tree} on the tree</span>}
      {node?.zero_found_error != null && (
        <span className="flex gap-1 text-[10px] text-muted-foreground">
          <span className="shrink-0">0 found</span>
          <span className="truncate" title={node.zero_found_error}>{node.zero_found_error}</span>
        </span>
      )}
    </button>
  )
}

export function TreeView({ data, selected, onSelect, folded, onToggleFold, hidden = new Set() }: Props) {
  const layout = useMemo(
    () => tidyLayout(data.nodes, data.links, data.roots, folded, hidden),
    [data, folded, hidden],
  )
  const parents = useMemo(() => new Set(data.links.map((l) => l.parent)), [data.links])
  const at = useMemo(() => new Map(layout.boxes.map((b) => [b.id, b])), [layout])
  const [view, setView] = useState({ x: 16, y: 8, k: 1 })
  const drag = useRef<{ x: number; y: number } | null>(null)

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest('button')) return
    drag.current = { x: e.clientX - view.x, y: e.clientY - view.y }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (drag.current) setView((v) => ({ ...v, x: e.clientX - drag.current!.x, y: e.clientY - drag.current!.y }))
  }
  const onWheel = (e: React.WheelEvent) =>
    setView((v) => ({ ...v, k: Math.min(2, Math.max(0.3, v.k * (e.deltaY < 0 ? 1.1 : 1 / 1.1))) }))

  return (
    <div
      className="relative min-h-0 flex-1 cursor-grab overflow-hidden rounded-lg border border-border bg-card active:cursor-grabbing"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={() => { drag.current = null }}
      onPointerLeave={() => { drag.current = null }}
      onWheel={onWheel}
    >
      <div
        className="absolute left-0 top-0 origin-top-left"
        style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`, width: layout.width, height: layout.height + HEADER_H }}
      >
        {data.levels.map((l) => (
          <div key={l.level} className="absolute truncate text-[10px] text-muted-foreground" style={{ left: (l.level + 1) * COL, top: 0, width: COL - 8 }} title={levelHeader(l)}>
            {levelHeader(l)}
          </div>
        ))}
        <svg className="pointer-events-none absolute left-0 top-0 overflow-visible" width={layout.width} height={layout.height + HEADER_H} aria-hidden>
          {layout.edges.map((e) => {
            const a = at.get(e.from)!
            const b = at.get(e.to)!
            return (
              <path
                key={`${e.from}>${e.to}`}
                d={curve(a.x + BOX_W, a.y + HEADER_H + BOX_H / 2, b.x, b.y + HEADER_H + BOX_H / 2)}
                fill="none"
                className="stroke-muted-foreground"
                strokeOpacity={at.get(e.to)!.faded ? 0.3 : 0.7}
                strokeDasharray={e.dashed ? '4 3' : undefined}
              />
            )
          })}
        </svg>
        {layout.boxes.map((b) => (
          <div key={b.id}>
            <BoxButton box={b} selected={selected === b.id} onSelect={onSelect} />
            {parents.has(b.id) && (
              <button
                type="button"
                aria-label={`${folded.has(b.id) ? 'Unfold' : 'Fold'} ${b.node?.title ?? b.root!.label}`}
                aria-expanded={!folded.has(b.id)}
                onClick={() => onToggleFold(b.id)}
                style={{ left: b.x + BOX_W - 2, top: b.y + HEADER_H + BOX_H / 2 - 7 }}
                className="absolute z-10 flex size-3.5 items-center justify-center rounded-full border border-border bg-background text-[9px] leading-none"
              >
                {folded.has(b.id) ? '+' : '−'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
