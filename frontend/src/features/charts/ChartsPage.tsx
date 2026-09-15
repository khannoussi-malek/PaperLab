import { Plus } from 'lucide-react'
import { useState } from 'react'
import type { ChartSummary } from '@/api/client'
import { useAllDatasets, useCharts, useChartMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { ModeToggle } from '@/components/mode-toggle'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { chartHref, datasetHref, newChartHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { datasetMeta } from '../data/datasetMeta'
import { NewDatasetDialog } from '../data/NewDatasetDialog'
import { ChartMenu } from './ChartMenu'
import { InlineTitle } from './InlineTitle'
import { TYPE_ICON } from './typeIcons'

const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 60 * 60 * 24 * 365],
  ['month', 60 * 60 * 24 * 30],
  ['week', 60 * 60 * 24 * 7],
  ['day', 60 * 60 * 24],
  ['hour', 60 * 60],
  ['minute', 60],
]

/** "2 hours ago", down to the minute; "just now" under a minute. */
function relativeTime(iso: string): string {
  const seconds = (Date.parse(iso) - Date.now()) / 1000
  for (const [unit, secondsPerUnit] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= secondsPerUnit) return rtf.format(Math.round(seconds / secondsPerUnit), unit)
  }
  return 'just now'
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

type RowProps = {
  chart: ChartSummary
  renaming: boolean
  onRename: () => void
  onSaveTitle: (title: string) => Promise<boolean>
  onStopRenaming: () => void
  onError: (message: string) => void
}

function ChartRow({ chart, renaming, onRename, onSaveTitle, onStopRenaming, onError }: RowProps) {
  const Icon = TYPE_ICON[chart.type]
  return (
    <li className="chart-row flex items-center gap-3 px-4 py-3" data-chart-id={chart.id}>
      <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        {renaming ? (
          <>
            {/* An input's value isn't DOM text, so `.chart-row` would stop matching its own title mid-rename
                (it's found by hasText, e.g. in e2e/charts-page.spec.ts) without this. */}
            <span className="sr-only">{chart.title}</span>
            <InlineTitle
              value={chart.title}
              label="Chart title"
              editing
              onEditingChange={(editing) => !editing && onStopRenaming()}
              onSave={onSaveTitle}
            />
          </>
        ) : (
          <a href={chartHref(chart.id)} title={chart.title} className="block truncate font-heading text-lg font-semibold hover:underline">
            {chart.title}
          </a>
        )}
        <p className="truncate text-sm text-muted-foreground">{chart.sources.join(', ')}</p>
        <p className="text-xs text-muted-foreground">
          Used in {plural(chart.note_count, 'note')} · edited {relativeTime(chart.updated_at)}
        </p>
      </div>
      <ChartMenu chart={chart} onRename={onRename} onError={onError} />
    </li>
  )
}

/** The library's own charts page: saved charts (rename, duplicate, delete) and the datasets of your own you built them from. */
export function ChartsPage() {
  const charts = useCharts()
  const datasets = useAllDatasets()
  const { update } = useChartMutations()
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [newDatasetOpen, setNewDatasetOpen] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const list = charts.data
  const ownDatasets = (datasets.data ?? []).filter((dataset) => dataset.kind === 'user')

  async function saveTitle(id: string, title: string) {
    await update.mutateAsync({ id, title })
    return true
  }

  return (
    <main className={cn('mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6', fadeIn)}>
      <header className="flex items-start justify-between gap-2">
        <div>
          <Button variant="ghost" size="sm" asChild className="-ml-2.5">
            <a href="#/">← Library</a>
          </Button>
          <h1 className="mt-1 font-heading text-3xl font-semibold">Charts</h1>
          {list && (
            <p className="text-sm text-muted-foreground">
              {plural(list.length, 'chart')} · {plural(ownDatasets.length, 'dataset')} of your own
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setNewDatasetOpen(true)}>
            New dataset
          </Button>
          <Button asChild>
            <a href={newChartHref()}>
              <Plus aria-hidden />
              New chart
            </a>
          </Button>
          <ModeToggle />
        </div>
      </header>

      {actionError && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{actionError}</AlertDescription>
        </Alert>
      )}

      {list === undefined ? (
        charts.isError ? (
          <p className="text-destructive">{charts.error.message}</p>
        ) : (
          <p className="text-muted-foreground">Loading…</p>
        )
      ) : list.length === 0 ? (
        <p className="text-muted-foreground">No charts yet. Build one from any data.</p>
      ) : (
        <Card className={cn('gap-0 py-0 ring-glass-border', glass)}>
          <ul className="divide-y divide-border">
            {list.map((chart) => (
              <ChartRow
                key={chart.id}
                chart={chart}
                renaming={renamingId === chart.id}
                onRename={() => setRenamingId(chart.id)}
                onSaveTitle={(title) => saveTitle(chart.id, title)}
                onStopRenaming={() => setRenamingId(null)}
                onError={setActionError}
              />
            ))}
          </ul>
        </Card>
      )}

      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-semibold">My data</h2>
        {datasets.isError ? (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{datasets.error.message}</AlertDescription>
            <AlertAction>
              <Button variant="outline" size="xs" onClick={() => void datasets.refetch()}>
                Retry
              </Button>
            </AlertAction>
          </Alert>
        ) : ownDatasets.length === 0 ? (
          <p className="text-sm text-muted-foreground">No datasets of your own yet.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {ownDatasets.map((dataset) => (
              <li key={dataset.id}>
                <a
                  href={datasetHref(dataset.id)}
                  className="own-dataset flex items-baseline gap-2 rounded-md px-2 py-1 hover:bg-foreground/5"
                >
                  <span className="truncate font-medium" title={dataset.name}>
                    {dataset.name}
                  </span>
                  <span className="shrink-0 text-sm text-muted-foreground tabular-nums">{datasetMeta(dataset)}</span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>

      <NewDatasetDialog open={newDatasetOpen} onOpenChange={setNewDatasetOpen} />
    </main>
  )
}
