import { useMemo, useRef, useState } from 'react'
import type { ProvenanceOut } from '@/api/client'
import { useBoxSize } from '@/features/graph/useBoxSize'
import { cn } from '@/lib/utils'
import { isUnknown, PARENT_NOT_RECORDED, tidyLayout } from './layout'
import { toRadial, RING } from './radial'
import { Legend } from './TreeView'
import { decisionKey, paperLabel, SVG_TONE } from './viewShared'

type Props = { data: ProvenanceOut; selected: string | null; onSelect: (id: string | null) => void; hidden: Set<string> }
const NODE_R = 5

/** How big is the search, and where does it spread: search roots in the centre, one ring per level. */
export function RadialView({ data, selected, onSelect, hidden }: Props) {
  const layout = useMemo(() => tidyLayout(data.nodes, data.links, data.roots, new Set(), hidden), [data, hidden])
  const boxes = useMemo(() => toRadial(layout), [layout])
  const at = useMemo(() => new Map(boxes.map((b) => [b.box.id, b])), [boxes])
  const [frame, size] = useBoxSize<HTMLDivElement>()
  const [view, setView] = useState({ x: 0, y: 0, k: 1 })
  const [tip, setTip] = useState<string | null>(null)
  const drag = useRef<{ x: number; y: number } | null>(null)
  const rings = useMemo(() => [...new Set(data.levels.map((l) => l.level))].sort((a, b) => a - b), [data.levels])
  const outer = Math.max(RING, ...boxes.map((b) => b.radius), ...rings.map((l) => (l + 1) * RING))
  const fit = size.width ? Math.min(2, (Math.min(size.width, size.height) / 2 - 24) / (outer + NODE_R)) : 1
  const scale = fit * view.k
  const tipBox = tip ? at.get(tip) : undefined
  // The hovered (else selected) paper's own way back to its search: every node on it, so the edge into each lights up.
  const path = useMemo(() => {
    const up = new Map(layout.edges.map((e) => [e.to, e.from]))
    const out = new Set<string>()
    for (let id = tip ?? selected; id; id = up.get(id) ?? null) out.add(id)
    return out
  }, [layout, tip, selected])

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <Legend />
      <div
        ref={frame}
        className="relative min-h-0 flex-1 cursor-grab overflow-hidden rounded-lg border border-border bg-card active:cursor-grabbing"
        onPointerDown={(e) => { if (!(e.target as Element).closest('[role="button"]')) drag.current = { x: e.clientX - view.x, y: e.clientY - view.y } }}
        onPointerMove={(e) => { if (drag.current) setView((v) => ({ ...v, x: e.clientX - drag.current!.x, y: e.clientY - drag.current!.y })) }}
        onPointerUp={() => { drag.current = null }}
        onPointerLeave={() => { drag.current = null }}
        onWheel={(e) => setView((v) => ({ ...v, k: Math.min(4, Math.max(0.3, v.k * (e.deltaY < 0 ? 1.1 : 1 / 1.1))) }))}
      >
        <svg width="100%" height="100%" role="group" aria-label="Radial view of the snowball tree">
          <g transform={`translate(${size.width / 2 + view.x} ${size.height / 2 + view.y}) scale(${scale})`}>
            {rings.map((l) => (
              <g key={l}>
                <circle r={(l + 1) * RING} fill="none" className="stroke-border" strokeDasharray="2 4" />
                <text y={-(l + 1) * RING - 4} textAnchor="middle" className="fill-muted-foreground" fontSize={12 / scale}>{`Level ${l}`}</text>
              </g>
            ))}
            {layout.edges.map((e) => {
              const a = at.get(e.from)!, b = at.get(e.to)!
              const on = path.has(e.to)
              return (
                <line
                  key={`${e.from}>${e.to}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="stroke-muted-foreground"
                  strokeOpacity={on ? 0.9 : b.box.faded ? 0.05 : 0.15} strokeWidth={on ? 1.8 : 1} strokeDasharray={e.dashed ? '4 3' : undefined}
                  vectorEffect="non-scaling-stroke"
                />
              )
            })}
            {boxes.map(({ box, x, y }) => {
              const { node } = box
              const label = node ? paperLabel(node, isUnknown(box.id) ? PARENT_NOT_RECORDED : node.title) : `${box.root!.label}, search`
              const pick = () => onSelect(box.id)
              return (
                <g
                  key={box.id} role="button" tabIndex={0} aria-label={label} aria-pressed={selected === box.id}
                  data-decision={node ? decisionKey(node) : 'root'} data-faded={box.faded}
                  transform={`translate(${x} ${y})`} className={cn('cursor-pointer outline-none', box.faded && 'opacity-35')}
                  onClick={pick} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick() } }}
                  onMouseEnter={() => setTip(box.id)} onMouseLeave={() => setTip(null)} onFocus={() => setTip(box.id)} onBlur={() => setTip(null)}
                >
                  <circle r={node ? NODE_R : 6} className={SVG_TONE[node ? decisionKey(node) : 'root']} strokeWidth={selected === box.id ? 3 : 1.5} vectorEffect="non-scaling-stroke" />
                  {node?.branch?.state === 'go_further' && <circle r={NODE_R + 3} fill="none" data-branch="go_further" className="stroke-included" strokeWidth={1.5} />}
                  {node?.branch?.state === 'stopped' && <circle r={NODE_R + 3} fill="none" data-branch="stopped" className="stroke-destructive" strokeWidth={1.5} strokeDasharray="2 2" />}
                </g>
              )
            })}
            {tipBox && (
              <text x={tipBox.x} y={tipBox.y - 12 / scale} textAnchor="middle" fontSize={12 / scale} className="pointer-events-none fill-foreground" stroke="var(--card)" strokeWidth={3} paintOrder="stroke">
                {tipBox.box.node ? (isUnknown(tipBox.box.id) ? PARENT_NOT_RECORDED : tipBox.box.node.title) : tipBox.box.root!.label}
              </text>
            )}
          </g>
        </svg>
      </div>
    </div>
  )
}
