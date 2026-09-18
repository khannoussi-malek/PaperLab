import { useEffect, useMemo, useRef, useState } from 'react'
import type { GraphLink, GraphNode } from '@/api/client'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/features/library/ErrorAlert'
import { CHART_INK, type ChartTheme } from '@/features/charts/palette'
import { carryPositions, endId, FADED, sizedNodes, tooltipFor, withAlpha, type SizedNode } from './graphModel'
import { useBoxSize } from './useBoxSize'

// Loaded on first use, exactly as PlotlyChart loads Plotly: react-force-graph-2d is 189 kB minified (61 kB gzipped)
// and only this page draws a graph. A failed dynamic import is cached by the browser for the page's lifetime, so the
// cache is cleared on failure and the error offers a reload.
let forceGraph: Promise<typeof import('react-force-graph-2d')> | null = null
function loadForceGraph() {
  if (!forceGraph) {
    forceGraph = import('react-force-graph-2d').catch((error: unknown) => {
      forceGraph = null
      throw error
    })
  }
  return forceGraph
}

/** react-force-graph mutates the objects it is given (x, y, vx, vy), so it gets its own copies, never cached data. */
type CanvasNode = SizedNode & { x?: number; y?: number }
type CanvasLink = {
  source: string | { id: string }
  target: string | { id: string }
  kind: GraphLink['kind']
  label: string | null
}

type Props = {
  nodes: GraphNode[]
  links: GraphLink[]
  theme: ChartTheme
  colors: Map<string, string>
  /** null: nothing focused, so nothing fades. */
  focused: Set<string> | null
  onSelect: (paperId: string) => void
}

export function GraphCanvas({ nodes, links, theme, colors, focused, onSelect }: Props) {
  const [Graph, setGraph] = useState<typeof import('react-force-graph-2d').default | null>(null)
  const [failed, setFailed] = useState(false)
  const [box, size] = useBoxSize<HTMLDivElement>()
  // K20: force-graph writes x/y onto the node objects it is given, so the last graph's objects know where every paper
  // is. A rebuild (a layer, the theme, a saved link) starts from there instead of throwing the layout again.
  const previous = useRef<CanvasNode[]>([])

  useEffect(() => {
    let cancelled = false
    loadForceGraph()
      .then((module) => !cancelled && setGraph(() => module.default))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [])

  const data = useMemo(() => {
    // oxlint-disable-next-line react/refs -- read once per rebuild, for where force-graph left each paper
    const canvasNodes: CanvasNode[] = carryPositions(sizedNodes(nodes, links, colors, theme), previous.current)
    const canvasLinks = links.map((link) => ({
      source: link.source,
      target: link.target,
      kind: link.kind,
      label: link.label ?? null,
    }))
    return { nodes: canvasNodes, links: canvasLinks }
  }, [nodes, links, colors, theme])

  useEffect(() => {
    previous.current = data.nodes
  }, [data])

  const ink = CHART_INK[theme].text

  if (failed) return <GraphLoadError />

  return (
    <div
      ref={box}
      aria-hidden
      data-view="2d"
      data-ready={Graph !== null}
      className="relative min-h-[28rem] flex-1 overflow-hidden rounded-xl"
    >
      {Graph === null || size.width === 0 ? (
        <div className="h-full w-full animate-pulse rounded-xl bg-muted" />
      ) : (
        <Graph
          width={size.width}
          height={size.height}
          graphData={data}
          backgroundColor="rgba(0,0,0,0)"
          nodeId="id"
          // react-force-graph-2d's TooltipContent type says a React element, but the force-graph it wraps declares
          // `Label = string | HTMLElement` and float-tooltip actually appends a raw HTMLElement — the wrapper's
          // .d.ts is wrong here, not the runtime.
          nodeLabel={(node: CanvasNode) => tooltipFor(node.title) as unknown as string}
          nodeRelSize={1}
          nodeVal={(node: CanvasNode) => node.radius * node.radius}
          nodeColor={(node: CanvasNode) =>
            focused !== null && !focused.has(node.id) ? withAlpha(node.color, FADED) : node.color
          }
          linkColor={(link: CanvasLink) => {
            const faded = focused !== null && !(focused.has(endId(link.source)) && focused.has(endId(link.target)))
            return withAlpha(link.kind === 'manual' ? ink : CHART_INK[theme].muted, faded ? FADED : 0.55)
          }}
          linkWidth={(link: CanvasLink) => (link.kind === 'manual' ? 2.5 : 1)}
          linkDirectionalArrowLength={(link: CanvasLink) => (link.kind === 'cites' || link.kind === 'manual' ? 4 : 0)}
          linkDirectionalArrowRelPos={1}
          linkCanvasObjectMode={(link: CanvasLink) => {
            const faded = focused !== null && !(focused.has(endId(link.source)) && focused.has(endId(link.target)))
            return link.kind === 'manual' && !faded ? 'after' : undefined
          }}
          linkCanvasObject={(link: CanvasLink, ctx: CanvasRenderingContext2D, scale: number) =>
            drawLinkLabel(link, ctx, scale, ink)
          }
          onNodeClick={(node: CanvasNode) => onSelect(node.id)}
          cooldownTicks={120}
        />
      )}
    </div>
  )
}

/** A failed dynamic import: the error and a way out, outside any aria-hidden wrapper so a screen reader reaches them. */
export function GraphLoadError() {
  return (
    <div className="grid min-h-[28rem] flex-1 place-items-center gap-2 p-6 text-center">
      <ErrorAlert message="The graph view could not load. Reload the page to try again." />
      <Button variant="outline" onClick={() => window.location.reload()}>
        Reload
      </Button>
    </div>
  )
}

/** The owner's own label, along its link. Skipped when zoomed far out, where it would be unreadable anyway. */
function drawLinkLabel(link: CanvasLink, ctx: CanvasRenderingContext2D, scale: number, ink: string) {
  const ends = link as unknown as { source: { x?: number; y?: number }; target: { x?: number; y?: number } }
  const { source, target } = ends
  if (!link.label || scale < 1 || source.x === undefined || target.x === undefined) return
  ctx.save()
  ctx.font = `${11 / scale}px "Atkinson Hyperlegible Next Variable", system-ui, sans-serif`
  ctx.fillStyle = ink
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(link.label, (source.x + target.x) / 2, ((source.y ?? 0) + (target.y ?? 0)) / 2)
  ctx.restore()
}
