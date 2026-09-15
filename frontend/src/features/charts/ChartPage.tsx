import { useChart } from '@/api/queries'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { ModeToggle } from '@/components/mode-toggle'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { chartsHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { ChartView } from './ChartView'

/** A saved chart's own page: its title and its live drawing. */
export function ChartPage({ chartId }: { chartId: string }) {
  const chart = useChart(chartId)
  const title = chart.data?.title ?? (chart.isError ? 'Chart not found' : 'Loading…')

  return (
    <main className={cn('mx-auto flex max-w-5xl flex-col gap-4 px-4 py-6', fadeIn)}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Button variant="ghost" size="sm" asChild className="-ml-2.5">
            <a href={chartsHref}>← Charts</a>
          </Button>
          <h1 className="mt-1 truncate font-heading text-3xl font-semibold" title={title}>
            {title}
          </h1>
        </div>
        <ModeToggle />
      </header>

      {chart.isError && (
        <p className="text-muted-foreground">
          This chart doesn't exist.{' '}
          <a href={chartsHref} className="text-primary hover:underline">
            Back to Charts
          </a>
          .
        </p>
      )}

      {chart.data && (
        <Card className={cn('ring-glass-border', glass)}>
          <CardContent>
            <ChartView spec={chart.data.spec} />
          </CardContent>
        </Card>
      )}
    </main>
  )
}
