import { useMemo, useState } from 'react'
import { useLibraryGraph, useWorkspaces } from '@/api/queries'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { ModeToggle } from '@/components/mode-toggle'
import { Button } from '@/components/ui/button'
import { useChartTheme } from '@/features/charts/useChartTheme'
import { LoadError } from '@/features/library/ErrorAlert'
import { cn } from '@/lib/utils'
import { GraphCanvas } from './GraphCanvas'
import { GraphControls } from './GraphControls'
import { GraphPanel } from './GraphPanel'
import { countsLine, DEFAULT_LAYERS, focusedIds, layerCounts, visibleLinks, workspaceColors, type LinkKind } from './graphModel'

const EMPTY =
  'No links yet. Import references, add papers to a workspace, or turn on OpenAlex to fill this in.'

export function GraphPage() {
  const [workspaceId, setWorkspaceId] = useState<string | null>(null)
  const [layers, setLayers] = useState<LinkKind[]>(DEFAULT_LAYERS)
  const [focusId, setFocusId] = useState<string | null>(null)
  const [hops, setHops] = useState(1)
  const theme = useChartTheme()
  const graph = useLibraryGraph(workspaceId)
  const workspaces = useWorkspaces()

  const nodes = useMemo(() => graph.data?.nodes ?? [], [graph.data])
  const allLinks = useMemo(() => graph.data?.links ?? [], [graph.data])
  const shown = useMemo(() => visibleLinks(allLinks, layers), [allLinks, layers])
  const counts = useMemo(() => layerCounts(allLinks), [allLinks])
  const colors = useMemo(() => workspaceColors(nodes, theme), [nodes, theme])
  const focused = useMemo(() => nodes.find((node) => node.id === focusId) ?? null, [nodes, focusId])
  const inFocus = useMemo(
    () => (focused === null ? null : focusedIds(shown, focused.id, hops)),
    [shown, focused, hops]
  )

  const toggleLayer = (kind: LinkKind) =>
    setLayers((current) => (current.includes(kind) ? current.filter((k) => k !== kind) : [...current, kind]))

  const counted = countsLine(nodes.length, shown.length)

  return (
    <main className={cn('mx-auto flex h-dvh max-w-7xl flex-col gap-4 px-4 py-6', fadeIn)}>
      <header className="flex items-center justify-between gap-2">
        <div>
          <h1 className="font-heading text-3xl font-semibold">Graph</h1>
          <p className="text-sm text-muted-foreground">
            {counted}
            {graph.data?.truncated && ' · Showing the first 2000 links.'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <a href="#/">Library</a>
          </Button>
          <ModeToggle />
        </div>
      </header>

      {graph.data === undefined ? (
        graph.isError ? (
          <LoadError message={graph.error.message} onRetry={() => void graph.refetch()} />
        ) : (
          <div className="h-full w-full animate-pulse rounded-xl bg-muted" />
        )
      ) : (
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[14rem_minmax(0,1fr)_20rem]">
          <div className={cn('min-h-0 overflow-y-auto rounded-xl border border-glass-border p-4', glass)}>
            <GraphControls
              counts={counts}
              layers={layers}
              onToggleLayer={toggleLayer}
              workspaces={workspaces.data ?? []}
              workspaceId={workspaceId}
              onWorkspace={(id) => {
                setWorkspaceId(id)
                setFocusId(null)
              }}
              colors={colors}
              nodes={nodes}
              hops={hops}
              onHops={setHops}
              focused={focused !== null}
            />
          </div>

          <div className={cn('flex min-h-0 flex-col rounded-xl border border-glass-border', glass)}>
            <p className="sr-only">{`${counted}. Use the papers list to explore connections.`}</p>
            {nodes.length === 0 || shown.length === 0 ? (
              <div className="grid flex-1 place-items-center px-6 text-center text-muted-foreground">{EMPTY}</div>
            ) : (
              <GraphCanvas
                nodes={nodes}
                links={shown}
                theme={theme}
                colors={colors}
                focused={inFocus}
                onSelect={setFocusId}
              />
            )}
          </div>

          <div className={cn('flex min-h-0 flex-col gap-3 rounded-xl border border-glass-border p-4', glass)}>
            <GraphPanel
              nodes={nodes}
              links={shown}
              focused={focused}
              onFocus={setFocusId}
              onClear={() => setFocusId(null)}
            />
          </div>
        </div>
      )}

    </main>
  )
}
