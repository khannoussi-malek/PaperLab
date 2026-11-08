import { useEffect, useMemo, useState } from 'react'
import type { ProvenanceOut } from '@/api/client'
import { Button } from '@/components/ui/button'
import { GraphLoadError } from '@/features/graph/GraphCanvas'
import { useBoxSize } from '@/features/graph/useBoxSize'
import { keyPaperIds, LEVEL_H, mapPositions, NO_YEAR_X, YEAR_W, yearTicks } from './mapModel'
import { Legend } from './TreeView'
import { decisionKey } from './viewShared'

// Loaded on first use, as GraphCanvas does; a failed import is retried on the next mount.
let forceGraph: Promise<typeof import('react-force-graph-2d')> | null = null
const load = () => (forceGraph ??= import('react-force-graph-2d').catch((e: unknown) => { forceGraph = null; throw e }))

type Props = { data: ProvenanceOut; selected: string | null; onSelect: (id: string | null) => void; hidden: Set<string> }
type MapNode = { id: string; title: string; level: number; year: number | null; paths: number; decision: ReturnType<typeof decisionKey>; branch: string | null; x: number; y: number; fx: number; fy: number }

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
const token = (name: string, fallback: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback

/** Which papers are central or foundational, by year. x is the year, y the level, fixed so the picture never jumps. */
export function MapView({ data, selected, onSelect, hidden }: Props) {
  const [Graph, setGraph] = useState<typeof import('react-force-graph-2d').default | null>(null)
  const [failed, setFailed] = useState(false)
  const [keys, setKeys] = useState(false)
  const [box, size] = useBoxSize<HTMLDivElement>()

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
  const ticks = useMemo(() => yearTicks(data.nodes), [data.nodes])
  const minYear = ticks[0]
  const bottom = (Math.max(0, ...data.nodes.map((n) => n.level)) + 1) * LEVEL_H + 20

  if (failed) return <GraphLoadError />
  const colors = { relevant: token('--included', '#15803d'), not_relevant: token('--destructive', '#dc2626'), none: token('--muted-foreground', '#64748b') }
  const ink = token('--foreground', '#111')
  const radius = (n: MapNode) => 3 + 2 * n.paths

  const paint = (n: MapNode, ctx: CanvasRenderingContext2D) => {
    const r = radius(n)
    ctx.globalAlpha = hidden.has(n.id) ? 0.25 : 1
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 2 * Math.PI); ctx.fillStyle = colors[n.decision]; ctx.fill()
    const ring = (extra: number, color: string, dash: number[] = []) => {
      ctx.beginPath(); ctx.setLineDash(dash); ctx.arc(n.x, n.y, r + extra, 0, 2 * Math.PI); ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([])
    }
    if (n.branch === 'go_further') ring(2.5, colors.relevant)
    if (n.branch === 'stopped') ring(2.5, colors.not_relevant, [2, 2])
    if (keys && key.has(n.id)) ring(6, ink)
    if (selected === n.id) ring(9, ink)
    ctx.globalAlpha = 1
  }
  const axis = (ctx: CanvasRenderingContext2D) => {
    ctx.save(); ctx.fillStyle = token('--muted-foreground', '#64748b'); ctx.font = '10px system-ui, sans-serif'; ctx.textAlign = 'center'
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
            linkColor={() => token('--muted-foreground', '#64748b')}
            linkLineDash={(l: { kind: string }) => (l.kind === 'cited_by' ? [4, 3] : null)}
            linkWidth={0.8}
            onNodeClick={(n: MapNode) => onSelect(n.id)}
            onRenderFramePost={axis}
            enableNodeDrag={false} cooldownTicks={0}
          />
        )}
      </div>
    </div>
  )
}
