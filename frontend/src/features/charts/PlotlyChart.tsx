import { useEffect, useRef } from 'react'
import type { Config, Data, Layout, PlotlyHTMLElement, PlotMouseEvent } from 'plotly.js-dist-min'

// Loaded on first use: Plotly is about 4.6 MB, and most views never draw a chart.
let plotly: Promise<typeof import('plotly.js-dist-min')> | null = null
const loadPlotly = () => (plotly ??= import('plotly.js-dist-min'))

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

  useEffect(() => {
    const div = ref.current
    if (!div) return
    let cancelled = false

    void loadPlotly().then(async (Plotly) => {
      if (cancelled) return
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
      const gd = await Plotly.react(div, traces, { ...layout, height, autosize: true }, config)
      if (cancelled) return
      gd.removeAllListeners('plotly_click')
      if (onPointClick) {
        gd.on('plotly_click', (event: PlotMouseEvent) => onPointClick(event.points[0]?.customdata))
      }
    })

    return () => {
      cancelled = true
      void loadPlotly().then((Plotly) => Plotly.purge(div))
    }
  }, [traces, layout, height, staticPlot, filename, onPointClick])

  return <div ref={ref} role="img" aria-label={label} />
}
