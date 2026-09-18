import { useEffect, useMemo, useRef, useState } from 'react'
import { CHART_INK } from '@/features/charts/palette'
import { GraphLoadError } from './GraphCanvas'
import { carryPositions, endId, FADED, sizedNodes, tooltipFor, withAlpha, type SizedNode } from './graphModel'
import { useBoxSize } from './useBoxSize'
import { hasWebGL, WEBGL_OFF, type ViewProps } from './viewModel'

// Loaded the first time 3D is picked, like 2D: react-force-graph-3d brings three.js, which no other view needs. This
// file is the only one that imports it. A failed dynamic import is cached for the page's lifetime, so the cache is
// cleared on failure and the error offers a reload.
let forceGraph3d: Promise<typeof import('react-force-graph-3d')> | null = null
function loadForceGraph3d() {
  if (!forceGraph3d) {
    forceGraph3d = import('react-force-graph-3d').catch((error: unknown) => {
      forceGraph3d = null
      throw error
    })
  }
  return forceGraph3d
}

/** react-force-graph-3d writes x/y/z and velocities onto the objects it is given, so it gets its own copies. */
type Node3D = SizedNode & { x?: number; y?: number; z?: number }
type Link3D = {
  source: string | { id: string }
  target: string | { id: string }
  kind: ViewProps['links'][number]['kind']
  label: string | null
}

/** Which clusters overlap in 2D (spec §5.2): free physics in three dimensions, orbit by dragging, zoom by scrolling. */
export function Graph3DView({ nodes, links, theme, colors, inFocus, onSelect }: ViewProps) {
  const [Graph, setGraph] = useState<typeof import('react-force-graph-3d').default | null>(null)
  const [failed, setFailed] = useState(false)
  // Asked once, before the canvas mounts: without WebGL three.js would throw inside React.
  const [webgl] = useState(() => hasWebGL())
  const [box, size] = useBoxSize<HTMLDivElement>()
  const previous = useRef<Node3D[]>([])

  useEffect(() => {
    let cancelled = false
    loadForceGraph3d()
      .then((module) => !cancelled && setGraph(() => module.default))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [])

  const data = useMemo(() => {
    // oxlint-disable-next-line react/refs -- read once per rebuild, for where the simulation left each paper
    const graphNodes: Node3D[] = carryPositions(sizedNodes(nodes, links, colors, theme), previous.current)
    const graphLinks = links.map((link) => ({
      source: link.source,
      target: link.target,
      kind: link.kind,
      label: link.label ?? null,
    }))
    return { nodes: graphNodes, links: graphLinks }
  }, [nodes, links, colors, theme])

  useEffect(() => {
    previous.current = data.nodes
  }, [data])

  if (failed) return <GraphLoadError />

  const ink = CHART_INK[theme]
  const fadedLink = (link: Link3D) =>
    inFocus !== null && !(inFocus.has(endId(link.source)) && inFocus.has(endId(link.target)))

  return (
    <div data-view="3d" data-ready={Graph !== null} className="flex min-h-0 flex-1 flex-col">
      {!webgl ? (
        <p className="grid min-h-[28rem] flex-1 place-items-center px-6 text-center text-muted-foreground">{WEBGL_OFF}</p>
      ) : (
        <div ref={box} aria-hidden className="relative min-h-[28rem] flex-1 overflow-hidden rounded-xl">
          {Graph === null || size.width === 0 ? (
            <div className="h-full w-full animate-pulse rounded-xl bg-muted" />
          ) : (
            <Graph
              width={size.width}
              height={size.height}
              graphData={data}
              backgroundColor="rgba(0,0,0,0)"
              showNavInfo={false}
              controlType="orbit"
              nodeId="id"
              // As in 2D: float-tooltip sets a string label as innerHTML, so a title only ever goes in as an element.
              nodeLabel={(node: Node3D) => tooltipFor(node.title) as unknown as string}
              nodeRelSize={1}
              nodeVal={(node: Node3D) => node.radius ** 3}
              nodeOpacity={1}
              nodeColor={(node: Node3D) =>
                inFocus !== null && !inFocus.has(node.id) ? withAlpha(node.color, FADED) : node.color
              }
              linkOpacity={1}
              linkColor={(link: Link3D) =>
                withAlpha(link.kind === 'manual' ? ink.text : ink.muted, fadedLink(link) ? FADED : 0.55)
              }
              // 0 draws a one-pixel line, the 2D view's 1; text along a 3D link would need another dependency, so a
              // `manual` link's label is its hover label instead.
              linkWidth={(link: Link3D) => (link.kind === 'manual' ? 2.5 : 0)}
              linkLabel={(link: Link3D) => (link.label ? tooltipFor(link.label) : null) as unknown as string}
              linkDirectionalArrowLength={(link: Link3D) => (link.kind === 'cites' || link.kind === 'manual' ? 4 : 0)}
              linkDirectionalArrowRelPos={1}
              onNodeClick={(node: Node3D) => onSelect(node.id)}
              cooldownTicks={120}
            />
          )}
        </div>
      )}
    </div>
  )
}
