import { ChartColumn, LoaderCircle } from 'lucide-react'
import type { ChartSummary } from '@/api/client'
import { useChart } from '@/api/queries'
import { glass } from '@/components/glass'
import { delayedIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { chartHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { chartMeta } from './chartMeta'
import { previewChartHeight } from './chartPreviewPanel'
import { ChartView } from './ChartView'

/**
 * The hovered or focused chart, drawn beside the list, like the library's `PaperPreview`. The list only carries a
 * chart's summary, so the spec is fetched here; React Query keeps each one, so going back over a row is free.
 * The drawing grows with the panel the reader drags, so a wider panel means a bigger chart, not a wider margin.
 */
export function ChartPreview({ chart, width }: { chart: ChartSummary; width: number }) {
  const full = useChart(chart.id)
  // The box keeps this height whether or not the chart has loaded, so the panel never jumps as you move down the list.
  const height = previewChartHeight(width)

  return (
    <aside
      aria-label="Chart preview"
      className={cn('chart-preview flex flex-col gap-4 rounded-xl p-4 ring-1 ring-glass-border', glass)}
    >
      {full.data ? (
        // staticPlot: a preview is for looking at. Clicking a point opens its source, which belongs on the chart's
        // own page, and a chart that swallowed the pointer would fight the row hover that opened it.
        <ChartView key={full.data.id} spec={full.data.spec} height={height} staticPlot withTable={false} />
      ) : (
        <div
          className="grid place-items-center rounded-sm bg-muted/60 text-sm text-muted-foreground"
          style={{ height }}
        >
          {full.isError ? (
            "Couldn't draw this chart."
          ) : (
            <LoaderCircle aria-hidden className={cn('motion-safe:animate-spin', delayedIn)} />
          )}
        </div>
      )}

      <div className="flex flex-col gap-1">
        <h2 className="font-heading text-xl leading-snug font-semibold wrap-anywhere">{chart.title}</h2>
        {chart.sources.length > 0 && <p className="text-sm">{chart.sources.join(', ')}</p>}
        <p className="text-xs text-muted-foreground">{chartMeta(chart)}</p>
      </div>

      <Button asChild variant="outline" className="self-start">
        <a href={chartHref(chart.id)}>
          <ChartColumn aria-hidden />
          Open chart
        </a>
      </Button>
    </aside>
  )
}
