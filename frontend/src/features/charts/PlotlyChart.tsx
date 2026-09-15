import { useEffect, useRef, useState } from 'react'
import type { Config, Data, Layout, PlotlyHTMLElement, PlotMouseEvent } from 'plotly.js-dist-min'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

// Loaded on first use: Plotly is about 4.6 MB, and most views never draw a chart. A failed import (a flaky network, a
// blocked request, a stale-deploy chunk 404) clears the cache: a browser's module loader caches even a *failed*
// dynamic import for the page's lifetime, so a same-page retry of the identical specifier replays the same
// rejection instantly, without ever touching the network again. Clearing the cache doesn't undo that (only a real
// reload does — see the error state's Retry below); it just keeps a stale rejection from haunting a future page
// load in the same browsing session.
let plotly: Promise<typeof import('plotly.js-dist-min')> | null = null
function loadPlotly() {
  if (!plotly) {
    plotly = import('plotly.js-dist-min').catch((error: unknown) => {
      plotly = null
      throw error
    })
  }
  return plotly
}

type Props = {
  traces: Data[]
  layout: Partial<Layout>
  height: number
  staticPlot?: boolean
  /** The wrapper's accessible name. The data table (`ChartDataTable`) is the accessible version of the plot itself. */
  label: string
  /** Base filename Plotly's mode bar downloads use. */
  filename: string
  onPointClick?: (customdata: unknown) => void
}

/** Draws a compiled chart with Plotly, loaded on first use. The only file that imports the runtime module. */
export function PlotlyChart({ traces, layout, height, staticPlot = false, label, filename, onPointClick }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const plotlyRef = useRef<typeof import('plotly.js-dist-min') | null>(null)
  // Read through a ref: a caller passing a fresh closure every render (as `ChartView` does) must never, by itself,
  // redraw the plot — that would purge and rebuild it, losing zoom/pan for a change that has nothing to do with data.
  const onPointClickRef = useRef(onPointClick)
  useEffect(() => {
    onPointClickRef.current = onPointClick
  })

  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    loadPlotly()
      .then((Plotly) => {
        if (cancelled) return
        plotlyRef.current = Plotly
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Draws or updates the plot whenever the figure actually changes. `Plotly.react` diffs against what's already
  // drawn, so it never purges on its own; an unrelated re-render that leaves these dependencies the same doesn't
  // even run this effect.
  useEffect(() => {
    const div = ref.current
    const Plotly = plotlyRef.current
    if (status !== 'ready' || !div || !Plotly) return
    let cancelled = false
    const svgButton = {
      name: 'Download SVG',
      title: 'Download SVG',
      icon: Plotly.Icons.disk,
      click: (gd: PlotlyHTMLElement) => Plotly.downloadImage(gd, { format: 'svg', filename, width: null, height: null }),
    }
    const config: Partial<Config> = {
      displaylogo: false,
      responsive: true,
      staticPlot,
      modeBarButtons: [['toImage', svgButton, layout.scene ? 'resetCameraDefault3d' : 'resetScale2d']],
      toImageButtonOptions: { format: 'png', filename },
    }
    void Plotly.react(div, traces, { ...layout, height, autosize: true }, config).then((gd) => {
      if (cancelled) return
      gd.removeAllListeners('plotly_click')
      gd.on('plotly_click', (event: PlotMouseEvent) => onPointClickRef.current?.(event.points[0]?.customdata))
    })
    return () => {
      cancelled = true
    }
  }, [status, traces, layout, height, staticPlot, filename])

  // Purges once, only when the component unmounts. The redraw effect above never tears the plot down on its own.
  // `div` is captured now, not read inside the cleanup: React nulls a host ref during unmount's mutation phase,
  // before this passive effect's cleanup runs, so `ref.current` would already be null by then. `plotlyRef` isn't a
  // host ref (React never touches it), so reading its latest value inside the cleanup is fine and necessary — the
  // module can still be loading when this effect first runs.
  useEffect(() => {
    const div = ref.current
    return () => {
      const Plotly = plotlyRef.current
      if (div && Plotly) Plotly.purge(div)
    }
  }, [])

  return (
    <div className="flex flex-col gap-3">
      {status === 'error' && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>The chart library didn't load.</AlertDescription>
          <AlertAction>
            {/* A same-page retry would replay the browser's own cached failure for this exact module (see above):
                only a real reload gets a clean module map and a fresh network request. */}
            <Button variant="outline" size="xs" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </AlertAction>
        </Alert>
      )}
      <div ref={ref} role="img" aria-label={label} />
    </div>
  )
}
