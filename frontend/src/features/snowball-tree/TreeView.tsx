import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight } from 'lucide-react'
import type { LevelStats, ProvenanceOut, ProvNode } from '@/api/client'
import { friendlySnowballError } from '@/features/workspace-search/snowballText'
import { cn } from '@/lib/utils'
import { BOX_H, BOX_W, COL, ROOT_W, PARENT_NOT_RECORDED, isUnknown, tidyLayout, type Box, type Layout } from './layout'
import { decisionWord, levelHeader } from './levelText'

type Props = {
  data: ProvenanceOut
  selected: string | null
  onSelect: (id: string | null) => void
  folded: Set<string>
  onToggleFold: (id: string) => void
  hidden?: Set<string>
  /** The box whose Find citing & cited papers call is running. */
  snowballing?: string | null
}

const titleOf = (box: Box) => (box.node ? (isUnknown(box.id) ? PARENT_NOT_RECORDED : box.node.title) : box.root!.label)

const HEADER_H = 52
const PAD_X = 16
const PAD_Y = 8
const EMPTY = new Set<string>()
export const TONE: Record<string, string> = {
  relevant: 'border-included bg-included/10',
  not_relevant: 'border-destructive bg-destructive/10',
  none: 'border-border bg-muted',
}
const curve = (x1: number, y1: number, x2: number, y2: number) => {
  const mid = (x1 + x2) / 2
  return `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`
}

const BRANCH_WORD: Record<string, string> = { go_further: 'go further', stopped: 'stopped' }

/** Open arrow = go further (directions on hover), bar = stopped (reason on hover). */
export function BranchMark({ branch }: { branch: NonNullable<ProvNode['branch']> }) {
  if (branch.state === 'go_further') {
    const dirs = branch.directions.map((d) => (d === 'cites' ? 'Its references' : 'Papers citing it')).join(', ')
    return <span aria-hidden data-branch="go_further" title={`Go further: ${dirs}`} className="shrink-0 text-included"><ArrowRight className="size-3" /></span>
  }
  return <span aria-hidden data-branch="stopped" title={branch.reason ? `Stopped: ${branch.reason}` : 'Stopped'} className="h-3 w-0.5 shrink-0 rounded bg-destructive" />
}

function BoxButton({ box, selected, busy, onSelect }: { box: Box; selected: boolean; busy: boolean; onSelect: (id: string) => void }) {
  const { node, root } = box
  const decision = node ? (node.decision === 'relevant' || node.decision === 'not_relevant' ? node.decision : 'none') : 'root'
  const branchWord = node?.branch ? BRANCH_WORD[node.branch.state] : undefined
  const label = node
    ? `${titleOf(box)}, level ${node.level}, ${decisionWord(node.decision)}${branchWord ? `, ${branchWord}` : ''}`
    : `${root!.label}, search`
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={selected}
      data-decision={decision}
      data-faded={box.faded}
      onClick={() => onSelect(box.id)}
      style={{ left: box.x, top: box.y + HEADER_H, width: root ? ROOT_W : BOX_W, height: BOX_H }}
      className={cn(
        'absolute flex flex-col justify-center overflow-hidden rounded-md border px-2 text-left text-xs transition-colors duration-150',
        TONE[decision] ?? 'border-border bg-card',
        box.faded && 'opacity-40',
        selected && 'ring-2 ring-ring',
      )}
    >
      <span className={cn('flex gap-1', root ? 'items-center' : 'items-start')}>
        <span className={cn('min-w-0 flex-1 font-medium', root ? 'truncate' : node?.zero_found_error != null ? 'line-clamp-1 break-words' : 'line-clamp-2 break-words')} title={titleOf(box)}>{titleOf(box)}</span>
        {node?.branch && <BranchMark branch={node.branch} />}
        {busy && <span className="shrink-0 text-[10px] text-muted-foreground">Snowballing…</span>}
        {node?.suggestion && <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-provenance-llm" />}
        {box.foldedMatches > 0 && <span className="shrink-0 text-[10px] text-muted-foreground">{box.foldedMatches} hidden</span>}
        {box.extraPaths > 0 && <span className="shrink-0 text-[10px] text-muted-foreground">+{box.extraPaths} other paths</span>}
      </span>
      {root && (
        <span className="truncate text-[10px] text-muted-foreground">
          {root.hit_count.toLocaleString('en')} hits · {root.on_tree} on the tree{root.excluded_hidden > 0 && ` · ${root.excluded_hidden} excluded hidden`}
        </span>
      )}
      {node?.zero_found_error != null && (
        <span className="flex gap-1 text-[10px] text-muted-foreground">
          <span className="shrink-0">0 found</span>
          {node.zero_found_error !== '' && (
            <span className="truncate" title={friendlySnowballError(node.zero_found_error)}>{friendlySnowballError(node.zero_found_error)}</span>
          )}
        </span>
      )}
    </button>
  )
}

type CanvasProps = {
  layout: Layout
  levels: LevelStats[]
  parents: Set<string>
  selected: string | null
  snowballing: string | null
  folded: Set<string>
  onSelect: (id: string) => void
  onToggleFold: (id: string) => void
}

/** The boxes and edges. Memoised so a pan or zoom (which only moves the wrapper's transform) never re-renders them. */
const Canvas = memo(function Canvas({ layout, levels, parents, selected, snowballing, folded, onSelect, onToggleFold }: CanvasProps) {
  const at = useMemo(() => new Map(layout.boxes.map((b) => [b.id, b])), [layout])
  return (
    <>
      {levels.map((l) => (
        <div key={l.level} className="absolute break-words text-[10px] leading-tight text-muted-foreground" style={{ left: (l.level + 1) * COL, top: 0, width: COL - 8 }} title={levelHeader(l)}>
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
              d={curve(a.x + (a.node ? BOX_W : ROOT_W), a.y + HEADER_H + BOX_H / 2, b.x, b.y + HEADER_H + BOX_H / 2)}
              fill="none"
              className="stroke-muted-foreground"
              strokeOpacity={b.faded ? 0.3 : 0.7}
              strokeDasharray={e.dashed ? '4 3' : undefined}
            />
          )
        })}
      </svg>
      {layout.boxes.map((b) => (
        <div key={b.id}>
          <BoxButton box={b} selected={selected === b.id} busy={snowballing === b.id} onSelect={onSelect} />
          {parents.has(b.id) && (
            <button
              type="button"
              aria-label={`${folded.has(b.id) ? 'Unfold' : 'Fold'} ${titleOf(b)}`}
              aria-expanded={!folded.has(b.id)}
              onClick={() => onToggleFold(b.id)}
              style={{ left: b.x + (b.node ? BOX_W : ROOT_W) - 2, top: b.y + HEADER_H + BOX_H / 2 - 7 }}
              className="absolute z-10 flex size-3.5 items-center justify-center rounded-full border border-border bg-background text-[9px] leading-none"
            >
              {folded.has(b.id) ? '+' : '−'}
            </button>
          )}
          {b.root && folded.has(b.id) && b.foldedMatches === 0 && b.childCount > 0 && (
            <button
              type="button"
              onClick={() => onToggleFold(b.id)}
              style={{ left: b.x, top: b.y + HEADER_H + BOX_H + 1 }}
              className="absolute text-[10px] leading-none text-muted-foreground underline"
            >
              {b.childCount} papers: show
            </button>
          )}
        </div>
      ))}
    </>
  )
})

function Swatch({ tone, label }: { tone: string; label: string }) {
  return <span className="flex items-center gap-1"><span aria-hidden className={cn('inline-block h-3 w-5 rounded-sm border', tone)} />{label}</span>
}
function Line({ dashed, label }: { dashed?: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <svg aria-hidden width="24" height="6"><line x1="0" y1="3" x2="24" y2="3" className="stroke-muted-foreground" strokeWidth="1.5" strokeDasharray={dashed ? '4 3' : undefined} /></svg>
      {label}
    </span>
  )
}

export function Legend() {
  return (
    <div aria-label="Legend" role="group" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      <Line label="it cites" />
      <Line dashed label="cited by" />
      <Swatch tone={TONE.relevant} label="included" />
      <Swatch tone={TONE.not_relevant} label="excluded" />
      <Swatch tone={TONE.none} label="not screened" />
    </div>
  )
}

export function TreeView({ data, selected, onSelect, folded, onToggleFold, hidden = EMPTY, snowballing = null }: Props) {
  const layout = useMemo(
    () => tidyLayout(data.nodes, data.links, data.roots, folded, hidden),
    [data, folded, hidden],
  )
  // A selected box that is no longer drawn (a refetch dropped it, or a fold hides it) is deselected.
  useEffect(() => {
    if (selected && !layout.boxes.some((b) => b.id === selected)) onSelect(null)
  }, [layout, selected, onSelect])
  const parents = useMemo(() => new Set(data.links.map((l) => l.parent)), [data.links])
  const [view, setView] = useState({ x: 16, y: 8, k: 1 })
  const frame = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number } | null>(null)

  // Pan so the first box that is not faded sits near the top-left, on first render and when a filter changes.
  const firstId = layout.boxes.find((b) => !b.faded)?.id
  const firstRef = useRef(layout)
  firstRef.current = layout
  useEffect(() => {
    const first = firstRef.current.boxes.find((b) => b.id === firstId)
    if (first) setView((v) => ({ ...v, x: PAD_X - first.x * v.k, y: PAD_Y - first.y * v.k }))
  }, [firstId, hidden.size])
  // A box picked from outside the canvas (keyboard focus, the "+N other paths" list) is panned into view.
  useEffect(() => {
    const box = selected ? firstRef.current.boxes.find((b) => b.id === selected) : undefined
    const el = frame.current
    if (!box || !el || !el.clientWidth) return
    setView((v) => {
      const w = (box.node ? BOX_W : ROOT_W) * v.k
      const h = BOX_H * v.k
      const sx = v.x + box.x * v.k
      const sy = v.y + (box.y + HEADER_H) * v.k
      const inside = sx >= 0 && sy >= 0 && sx + w <= el.clientWidth && sy + h <= el.clientHeight
      return inside ? v : { ...v, x: PAD_X - box.x * v.k, y: PAD_Y - box.y * v.k }
    })
  }, [selected])

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
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <Legend />
      <div
        ref={frame}
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
          <Canvas
            layout={layout} levels={data.levels} parents={parents} selected={selected} snowballing={snowballing}
            folded={folded} onSelect={onSelect} onToggleFold={onToggleFold}
          />
        </div>
      </div>
    </div>
  )
}
