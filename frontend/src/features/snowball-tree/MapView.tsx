import { useEffect, useMemo, useRef, useState } from 'react'
import type { ProvenanceOut } from '@/api/client'
import { Button } from '@/components/ui/button'
import { endId, withAlpha } from '@/features/graph/graphModel'
import { GraphLoadError } from '@/features/graph/GraphCanvas'
import { useBoxSize } from '@/features/graph/useBoxSize'
import { isUnknown } from './layout'
import { bandHeight, keyPaperIds, mapPositions, NO_YEAR_X, tickX, YEAR_W, yearTicks } from './mapModel'
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

  // "Parent not recorded" boxes are not papers: no year, no place on a timeline.
  const nodes = useMemo(() => data.nodes.filter((n) => !isUnknown(n.id)), [data.nodes])
  const key = useMemo(() => keyPaperIds(nodes, 10, hidden), [nodes, hidden])
  const keyList = useMemo(() => nodes.filter((n) => key.has(n.id)).sort((a, b) => b.paths - a.paths || a.id.localeCompare(b.id)), [nodes, key])
  // Make the picture as tall as the canvas allows: its width is fixed by the years, so y gets width * (h / w), less 30% margins.
  // Measured once, so opening the side panel or a refetch never relays the picture out.
  const years = nodes.flatMap((n) => (n.year ? [n.year] : []))
  const xExtent = ((years.length ? Math.max(...years) - Math.min(...years) : 0) + 3.5) * YEAR_W
  const frozen = useRef<number | undefined>(undefined)
  if (frozen.current === undefined && size.width) frozen.current = Math.max(200, (xExtent * size.height) / size.width * 0.7)
  const spread = frozen.current
  const graph = useMemo(() => {
    const at = mapPositions(nodes, spread)
    const placed: MapNode[] = nodes.map((n) => {
      const { x, y } = at.get(n.id)!
      return { id: n.id, title: n.title, level: n.level, year: n.year ?? null, paths: n.paths, decision: decisionKey(n), branch: n.branch?.state ?? null, x, y, fx: x, fy: y }
    })
    const ids = new Set(placed.map((n) => n.id))
    const links = data.links.filter((l) => ids.has(l.parent) && ids.has(l.child)).map((l) => ({ source: l.parent, target: l.child, kind: l.kind }))
    return { nodes: placed, links }
  }, [nodes, data.links, spread])
  const noYear = useMemo(() => new Set(nodes.filter((n) => !n.year).map((n) => n.id)), [nodes])
  const ticks = useMemo(() => yearTicks(nodes), [nodes])
  const band = bandHeight(nodes, spread)
  const levels = Array.from({ length: Math.max(0, ...nodes.map((n) => n.level)) + 1 }, (_, i) => i)
  const bottom = (levels.length - 0.5) * band + 30

  // Fit the picture to the canvas once, when it is first drawn; the Fit button does it again on demand.
  const ready = Graph !== null && size.width > 0
  const fitted = useRef(false)
  const fit = () => graphRef.current?.zoomToFit(0, 70)
  useEffect(() => {
    if (!ready || fitted.current) return
    const t = setTimeout(() => { fit(); fitted.current = true }, 60)
    return () => clearTimeout(t)
  }, [ready, graph]) // eslint-disable-line react-hooks/exhaustive-deps

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
    for (const y of ticks) ctx.fillText(String(y), tickX(nodes, y), bottom)
    if (noYear.size > 0) ctx.fillText('No year', NO_YEAR_X, bottom)
    ctx.textAlign = 'right'
    for (const l of levels) ctx.fillText(`Level ${l}`, NO_YEAR_X - YEAR_W * 0.6, l * band)
    ctx.restore()
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <Legend />
      <div>
        <Button type="button" size="sm" variant="outline" aria-pressed={keys} onClick={() => setKeys((v) => !v)}>Key papers</Button>
        <Button type="button" size="sm" variant="outline" className="ml-2" onClick={fit}>Fit</Button>
        {keys && (
          <span className="ml-2 text-xs text-muted-foreground">
            {keyList.length > 0 ? 'The papers with the most routes in (up to 10) are ringed.' : 'No paper is reached by more than one route yet. Key papers appear as snowballing links them.'}
          </span>
        )}
        {keys && keyList.length > 0 && (
          <ul aria-label="Key papers" className="mt-2 flex flex-wrap gap-1.5">
            {keyList.map((n) => (
              <li key={n.id}><Button type="button" size="sm" variant="ghost" className="h-6 max-w-56 truncate px-2 text-xs" onClick={() => onSelect(n.id)}>{n.title}</Button></li>
            ))}
          </ul>
        )}
      </div>
      <div ref={box} aria-label="Map of the snowball tree" role="group" className="relative min-h-[20rem] flex-1 overflow-hidden rounded-lg border border-border bg-card">
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
              const [a, b] = [endId(l.source), endId(l.target)]
              return withAlpha(muted, lit ? 0.9 : hidden.has(a) || hidden.has(b) || noYear.has(a) || noYear.has(b) ? 0.05 : 0.14)
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
