import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { ForceGraphMethods, LinkObject, NodeObject } from 'react-force-graph-3d'
import { CHART_INK } from '@/features/charts/palette'
import { GraphLoadError } from './GraphCanvas'
import { carryPositions, endId, FADED, nodeLabel, sizedNodes, tooltipFor, withAlpha, type SizedNode } from './graphModel'
import { useBoxSize } from './useBoxSize'
import { drawsPapers, particlesFor } from './paperModel'
import { hasWebGL, WEBGL_FAILED, WEBGL_OFF, type ViewProps } from './viewModel'

// Loaded the first time 3D is picked, like 2D: react-force-graph-3d brings three.js, which no other view needs. This
// file is the only one that imports it. A failed dynamic import is cached for the page's lifetime, so the cache is
// cleared on failure and the error offers a reload.
// The paper pages (paperNodes, three.js) come in the same load, so three.js still stays out of every other view.
type Loaded = [typeof import('react-force-graph-3d'), typeof import('./paperNodes')]
let forceGraph3d: Promise<Loaded> | null = null
function loadForceGraph3d() {
  if (!forceGraph3d) {
    forceGraph3d = Promise.all([import('react-force-graph-3d'), import('./paperNodes')] as const).catch((error: unknown) => {
      forceGraph3d = null
      throw error
    })
  }
  return forceGraph3d
}

// Asked once per page load, not once per mount: the probe releases its context (viewModel's hasWebGL), but there's
// still no reason to ask again on every view switch. Reused for the rest of the page's life.
let webgl: boolean | undefined

type BoundaryState = { failed: boolean }

/**
 * Catches a 3D start-up failure the WebGL probe in `hasWebGL` can't predict: a lost context, a driver crash, or the
 * browser's cap on live WebGL contexts. three-forcegraph's `WebGLRenderer` throws inside a `useLayoutEffect` on
 * mount, and the app has no error boundary elsewhere, so this one wraps only the box that mounts `<Graph>` — the
 * rest of the page, including the tabs above it, is untouched. No logging: the failure has nowhere useful to go.
 */
class CanvasBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { failed: false }

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true }
  }

  render() {
    // Outside any aria-hidden wrapper, exactly like the WebGL-off message: a screen reader must still reach it.
    if (this.state.failed) {
      return (
        <p className="grid min-h-[28rem] flex-1 place-items-center px-6 text-center text-muted-foreground">
          {WEBGL_FAILED}
        </p>
      )
    }
    return this.props.children
  }
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
  const [papers, setPapers] = useState<typeof import('./paperNodes') | null>(null)
  const [failed, setFailed] = useState(false)
  // Asked once, before the canvas mounts: without WebGL three.js would throw inside React.
  const [webglSupported] = useState(() => (webgl ??= hasWebGL()))
  const [box, size] = useBoxSize<HTMLDivElement>()
  const previous = useRef<Node3D[]>([])
  const graphRef = useRef<ForceGraphMethods<NodeObject<Node3D>, LinkObject<Node3D, Link3D>> | undefined>(undefined)
  // Fit once per mount, when the layout first settles: a later rebuild (a layer toggle, a theme change) must never
  // yank a camera the owner has moved. A view switch remounts this component (Radix drops the unpicked tab), so
  // returning to 3D fits again.
  const fitted = useRef(false)

  useEffect(() => {
    let cancelled = false
    loadForceGraph3d()
      .then(([module, paperNodes]) => {
        if (cancelled) return
        setGraph(() => module.default)
        setPapers(paperNodes)
      })
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

  // Each paper drawn as a small page in its workspace colour; the papers around a selected one glow. Above the
  // limit the plain spheres stay (undefined keeps the library's default).
  const paperObject = useCallback(
    (node: Node3D) => papers!.paperObject(node.color, node.radius, inFocus !== null && !inFocus.has(node.id), inFocus !== null && inFocus.has(node.id)),
    [papers, inFocus],
  )
  const showPapers = papers !== null && drawsPapers(data.nodes.length)

  // Fog into the app's background, from the fitted camera's distance: far papers fade. Theme changes recolour it.
  const fogged = useRef(false)
  const addFog = () => {
    const graph = graphRef.current
    if (!graph || !papers) return
    graph.scene().fog = papers.fogFor(graph.camera().position.length())
    fogged.current = true
  }
  useEffect(() => {
    const fog = graphRef.current?.scene().fog
    if (fogged.current && fog && papers) fog.color.copy(papers.pageBackground())
  }, [theme, papers])

  if (failed) return <GraphLoadError />

  const ink = CHART_INK[theme]
  const fadedLink = (link: Link3D) =>
    inFocus !== null && !(inFocus.has(endId(link.source)) && inFocus.has(endId(link.target)))

  return (
    <div data-view="3d" data-ready={Graph !== null} className="flex min-h-0 flex-1 flex-col">
      {!webglSupported ? (
        <p className="grid min-h-[28rem] flex-1 place-items-center px-6 text-center text-muted-foreground">{WEBGL_OFF}</p>
      ) : (
        <CanvasBoundary>
          <div ref={box} aria-hidden className="relative min-h-[28rem] flex-1 overflow-hidden rounded-xl">
            {Graph === null || size.width === 0 ? (
              <div className="h-full w-full animate-pulse rounded-xl bg-muted" />
            ) : (
              <Graph
                ref={graphRef}
                width={size.width}
                height={size.height}
                graphData={data}
                backgroundColor="rgba(0,0,0,0)"
                showNavInfo={false}
                controlType="orbit"
                nodeId="id"
                // As in 2D: float-tooltip sets a string label as innerHTML, so a title only ever goes in as an element.
                nodeLabel={(node: Node3D) => tooltipFor(nodeLabel(node)) as unknown as string}
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
                // 0 draws a one-pixel line, the 2D view's 1; text along a 3D link would need another dependency, so
                // a `manual` link's label is its hover label instead.
                linkWidth={(link: Link3D) => (link.kind === 'manual' ? 2.5 : 0)}
                linkLabel={(link: Link3D) => (link.label ? tooltipFor(link.label) : null) as unknown as string}
                linkDirectionalArrowLength={(link: Link3D) => (link.kind === 'cites' || link.kind === 'manual' ? 4 : 0)}
                linkDirectionalArrowRelPos={1}
                nodeThreeObject={showPapers ? paperObject : undefined}
                // Pulses run along citations, from the citing paper to the cited one (blue: the brand's citations).
                linkDirectionalParticles={(link: Link3D) => particlesFor(link.kind, fadedLink(link))}
                linkDirectionalParticleWidth={1.8}
                linkDirectionalParticleSpeed={0.006}
                linkDirectionalParticleColor={() => (theme === 'dark' ? '#60a5fa' : '#2563eb')}
                onNodeClick={(node: Node3D) => onSelect(node.id)}
                onEngineStop={() => {
                  if (fitted.current) return
                  fitted.current = true
                  graphRef.current?.zoomToFit(400, 40)
                  // After the fit's 400 ms flight, so the fog starts where the camera settled.
                  window.setTimeout(addFog, 450)
                }}
                cooldownTicks={120}
              />
            )}
          </div>
        </CanvasBoundary>
      )}
    </div>
  )
}
