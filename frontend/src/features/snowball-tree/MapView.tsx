import { useEffect, useMemo, useRef, useState } from 'react'
import type { ProvenanceOut } from '@/api/client'
import { Button } from '@/components/ui/button'
import { endId, withAlpha } from '@/features/graph/graphModel'
import { GraphLoadError } from '@/features/graph/GraphCanvas'
import { useBoxSize } from '@/features/graph/useBoxSize'
import { keyPaperIds, LEVEL_H, mapPositions, NO_YEAR_X, YEAR_W, yearTicks } from './mapModel'
import { Legend } from './TreeView'
import { decisionKey } from './viewShared'

// Loaded on first use, as GraphCanvas does; a failed import is retried on the next mount.
let forceGraph: Promise<typeof import('react-force-graph-2d')> | null = null
const load = () => (forceGraph ??= import('react-force-graph-2d').catch((e: unknown) => { forceGraph = null; throw e }))

type Props = { data: ProvenanceOut; selected: string | null; onSelect: (id: string | null) => void; hidden: Set<string> }
type MapLink = { source: string | { id: string }; target: string | { id: string }; kind: string }
type MapNode = { id: string; title: string; level: number; year: number | null; paths: number; decision: ReturnType<typeof decisionKey>; branch: string | null; x: number; y: number; fx: number; fy: number }

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
const token = (name: string, fallback: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback

/** Which papers are central or foundational, by year. x is the year, y the level, fixed so the picture never jumps. */
export function MapView({ data, selected, onSelect, hidden }: Props) {
  const [Graph, setGraph] = useState<typeof import('react-force-graph-2d').default | null>(null)
  const [failed, setFailed] = useState(false)
  const [keys, setKeys] = useState(false)
  const [box, size] = useBoxSize<HTMLDivElement>()
  const [hover, setHover] = useState<string | null>(null)
  const graphRef = useRef<{ zoomToFit: (ms?: number, pad?: number) => void } | undefined>(undefined)

  useEffect(() => {
    let off = false
    load().then((m) => !off && setGraph(() => m.default)).catch(() => !off && setFailed(true))
    return () => { off = true }
  }, [])

  const key = useMemo(() => keyPaperIds(data.nodes), [data.nodes])
  const graph = useMemo(() => {
    const at = mapPositions(data.nodes)
    const nodes: MapNode[] = data.nodes.map((n) => {
      const { x, y } = at.get(n.id)!
      return { id: n.id, title: n.title, level: n.level, year: n.year ?? null, paths: n.paths, decision: decisionKey(n), branch: n.branch?.state ?? null, x, y, fx: x, fy: y }
    })
    const ids = new Set(nodes.map((n) => n.id))
    const links = data.links.filter((l) => ids.has(l.parent) && ids.has(l.child)).map((l) => ({ source: l.parent, target: l.child, kind: l.kind }))
    return { nodes, links }
  }, [data])
  const noYear = useMemo(() => new Set(data.nodes.filter((n) => !n.year).map((n) => n.id)), [data.nodes])
  const ticks = useMemo(() => yearTicks(data.nodes), [data.nodes])
  const minYear = ticks[0]
  const bottom = (Math.max(0, ...data.nodes.map((n) => n.level)) + 0.5) * LEVEL_H + 40

  // Fit the picture to the canvas once the nodes sit where they are going to stay.
  const ready = Graph !== null && size.width > 0
  useEffect(() => {
    if (!ready) return
    const t = setTimeout(() => graphRef.current?.zoomToFit(0, 50), 60)
    return () => clearTimeout(t)
  }, [ready, graph, size.width, size.height])

  if (failed) return <GraphLoadError />
  const colors = { relevant: token('--included', '#15803d'), not_relevant: token('--destructive', '#dc2626'), none: token('--muted-foreground', '#64748b') }
  const ink = token('--foreground', '#111')
  const radius = (n: MapNode) => 3 + 2 * n.paths
  const active = hover ?? selected
  const muted = token('--muted-foreground', '#64748b').startsWith('#') ? token('--muted-foreground', '#64748b') : '#64748b'

  const paint = (n: MapNode, ctx: CanvasRenderingContext2D, scale: number) => {
    const r = radius(n)
    ctx.globalAlpha = hidden.has(n.id) ? 0.25 : 1
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI); ctx.fillStyle = colors[n.decision]; ctx.fill()
    const ring = (extra: number, color: string, dash: number[] = []) => {
      ctx.beginPath(); ctx.setLineDash(dash); ctx.arc(n.x, n.y, r + extra, 0, 2 * Math.PI); ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([])
    }
    if (n.branch === 'go_further') ring(2.5, colors.relevant)
    if (n.branch === 'stopped') ring(2.5, colors.not_relevant, [2, 2])
    if (keys && key.has(n.id)) {
      ring(6, ink)
      ctx.fillStyle = ink; ctx.font = `${11 / scale}px system-ui, sans-serif`; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
      ctx.fillText(n.title.length > 28 ? `${n.title.slice(0, 27)}…` : n.title, n.x + r + 9, n.y)
    }
    if (selected === n.id) ring(9, ink)
    ctx.globalAlpha = 1
  }
  const axis = (ctx: CanvasRenderingContext2D, scale: number) => {
    ctx.save(); ctx.fillStyle = token('--muted-foreground', '#64748b'); ctx.font = `${12 / scale}px system-ui, sans-serif`; ctx.textAlign = 'center'
    for (const y of ticks) ctx.fillText(String(y), (y - minYear) * YEAR_W, bottom)
    if (data.nodes.some((n) => !n.year)) ctx.fillText('No year', NO_YEAR_X, bottom)
    ctx.restore()
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <Legend />
      <div>
        <Button type="button" size="sm" variant="outline" aria-pressed={keys} onClick={() => setKeys((v) => !v)}>Key papers</Button>
        {keys && <span className="ml-2 text-xs text-muted-foreground">The 10 papers with the most routes in are ringed.</span>}
      </div>
      <div ref={box} className="relative min-h-[20rem] flex-1 overflow-hidden rounded-lg border border-border bg-card">
        {Graph === null || size.width === 0 ? (
          <div className="h-full w-full animate-pulse bg-muted" />
        ) : (
          <Graph
            width={size.width} height={size.height} graphData={graph} nodeId="id" backgroundColor="rgba(0,0,0,0)"
            nodeRelSize={1}
            nodeLabel={(n: MapNode) => `${esc(n.title)}<br/>${n.year ?? 'no year'} · Level ${n.level}` as unknown as string}
            nodeCanvasObject={paint}
            nodePointerAreaPaint={(n: MapNode, color: string, ctx: CanvasRenderingContext2D) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(n.x, n.y, radius(n) + 2, 0, 2 * Math.PI); ctx.fill() }}
            ref={graphRef as never}
            linkColor={(l: MapLink) => {
              const lit = active !== null && (endId(l.source) === active || endId(l.target) === active)
              return withAlpha(muted, lit ? 0.9 : noYear.has(endId(l.source)) || noYear.has(endId(l.target)) ? 0.05 : 0.14)
            }}
            linkLineDash={(l: MapLink) => (l.kind === 'cited_by' ? [4, 3] : null)}
            linkWidth={(l: MapLink) => (active !== null && (endId(l.source) === active || endId(l.target) === active) ? 1.8 : 0.8)}
            onNodeHover={(n: MapNode | null) => setHover(n ? n.id : null)}
            onNodeClick={(n: MapNode) => onSelect(n.id)}
            onRenderFramePost={axis}
            enableNodeDrag={false} cooldownTicks={0}
          />
        )}
      </div>
    </div>
  )
}
