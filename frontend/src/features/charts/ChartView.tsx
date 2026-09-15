import { TriangleAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { ChartSpec } from '@/api/client'
import { useResolvedChart } from '@/api/queries'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ChartDataTable } from './ChartDataTable'
import { chartTable } from './chartTable'
import { compileChart } from './compile'
import { decodePoint, pointSource, sourceHref } from './points'
import { PlotlyChart } from './PlotlyChart'
import { useChartTheme } from './useChartTheme'

type Props = {
  spec: ChartSpec
  height?: number
  staticPlot?: boolean
  withTable?: boolean
}

/** Draws a chart spec's live data: resolves it, compiles it for the current theme, and opens a clicked point's source. */
export function ChartView({ spec, height = 360, staticPlot = false, withTable = true }: Props) {
  const theme = useChartTheme()
  const resolved = useResolvedChart(spec)
  const [showTable, setShowTable] = useState(false)
  // While a changed spec resolves, `drawn` is still the previous spec with its own data: that drawing stays up, and its
  // warnings stay hidden, since they describe the previous spec rather than this one.
  const drawn = resolved.data
  const compiled = useMemo(() => (drawn ? compileChart(drawn.spec, drawn.data, theme) : null), [drawn, theme])
  const warnings = resolved.isPlaceholderData ? [] : (compiled?.warnings ?? [])

  function openSource(customdata: unknown) {
    const ref = decodePoint(customdata)
    if (!ref || !drawn) return
    const source = pointSource(drawn.data, ref)
    // Assigned, not `location.replace`: Back from the opened source returns here.
    if (source) window.location.hash = sourceHref(source)
  }

  return (
    <div className="flex flex-col gap-3">
      {resolved.error && (
        <Alert variant="destructive" className={cn('border-glass-border')}>
          <AlertDescription>{resolved.error.message}</AlertDescription>
          <AlertAction>
            <Button variant="outline" size="xs" onClick={() => void resolved.refetch()}>
              Retry
            </Button>
          </AlertAction>
        </Alert>
      )}

      {warnings.map((warning) => (
        <p key={warning} role="status" className="chart-warning flex items-center gap-1.5 text-sm text-muted-foreground">
          <TriangleAlert aria-hidden className="size-4" />
          {warning}
        </p>
      ))}

      <div
        className="chart-view w-full"
        data-chart-type={spec.type}
        data-series-count={compiled?.seriesCount ?? 0}
        style={{ minHeight: height }}
      >
        {compiled && (
          <div className={cn(resolved.isPlaceholderData && 'opacity-60')}>
            <PlotlyChart
              traces={compiled.traces}
              layout={compiled.layout}
              height={height}
              staticPlot={staticPlot}
              label={`${spec.type} chart`}
              filename={`chart-${spec.type}`}
              onPointClick={openSource}
            />
          </div>
        )}
      </div>

      {withTable && drawn && (
        <div className="flex flex-col gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="self-start"
            aria-expanded={showTable}
            onClick={() => setShowTable((shown) => !shown)}
          >
            View data table
          </Button>
          {showTable && <ChartDataTable view={chartTable(drawn.spec, drawn.data)} />}
        </div>
      )}
    </div>
  )
}
