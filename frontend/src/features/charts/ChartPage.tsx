import { useState } from 'react'
import { useChart, useChartMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { ModeToggle } from '@/components/mode-toggle'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { chartsHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { ChartMenu } from './ChartMenu'
import { ChartView } from './ChartView'
import { InlineTitle } from './InlineTitle'

/** A saved chart's own page: its renameable title, its actions menu, and its live drawing. */
export function ChartPage({ chartId }: { chartId: string }) {
  const chart = useChart(chartId)
  const { update } = useChartMutations()
  const [renaming, setRenaming] = useState(false)
  const title = chart.data?.title ?? (chart.isError ? 'Chart not found' : 'Loading…')

  async function saveTitle(next: string) {
    await update.mutateAsync({ id: chartId, title: next })
    return true
  }

  return (
    <main className={cn('mx-auto flex max-w-5xl flex-col gap-4 px-4 py-6', fadeIn)}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Button variant="ghost" size="sm" asChild className="-ml-2.5">
            <a href={chartsHref}>← Charts</a>
          </Button>
          {chart.data ? (
            <InlineTitle as="h1" value={chart.data.title} label="Chart title" editing={renaming} onEditingChange={setRenaming} onSave={saveTitle} />
          ) : (
            <h1 className="mt-1 truncate font-heading text-3xl font-semibold" title={title}>
              {title}
            </h1>
          )}
        </div>
        <div className="flex items-center gap-2">
          {chart.data && (
            <ChartMenu chart={{ id: chart.data.id, title: chart.data.title, note_count: chart.data.note_ids.length }} onRename={() => setRenaming(true)} />
          )}
          <ModeToggle />
        </div>
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
