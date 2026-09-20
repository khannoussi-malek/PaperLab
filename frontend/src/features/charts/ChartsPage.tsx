import { Plus } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import type { ChartSummary } from '@/api/client'
import { useAllDatasets, useCharts, useChartMutations } from '@/api/queries'
import { AppShell } from '@/components/AppShell'
import { glass } from '@/components/glass'
import { delayedIn } from '@/components/motion'
import { PanelResizeHandle } from '@/components/PanelResizeHandle'
import { loadPanelWidth, panelTrack, savePanelWidth } from '@/components/panelWidth'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { chartHref, datasetHref, newChartHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { datasetMeta } from '../data/datasetMeta'
import { NewDatasetDialog } from '../data/NewDatasetDialog'
import { browserStorage } from '../notes/highlightColors'
import { ChartMenu } from './ChartMenu'
import { chartMeta, plural } from './chartMeta'
import { CHART_PREVIEW } from './chartPreviewPanel'
import { ChartPreview } from './ChartPreview'
import { InlineTitle } from './InlineTitle'
import { warmPlotly } from './loadPlotly'
import { TYPE_ICON } from './typeIcons'

/** Skimming the list with the mouse shouldn't fetch and draw a chart for every row it crosses. */
const HOVER_PREVIEW_DELAY_MS = 150
/** `AppShell`'s `p-3` on the view pane, which sits between the preview's right edge and the window's. */
const PANE_PADDING_PX = 12

type RowProps = {
  chart: ChartSummary
  renaming: boolean
  previewed: boolean
  onPreview: (id: string, immediate: boolean) => void
  onRename: () => void
  onSaveTitle: (title: string) => Promise<boolean>
  onStopRenaming: () => void
  onError: (message: string) => void
}

function ChartRow({ chart, renaming, previewed, onPreview, onRename, onSaveTitle, onStopRenaming, onError }: RowProps) {
  const Icon = TYPE_ICON[chart.type]
  return (
    <li
      className={cn(
        'chart-row flex items-center gap-3 px-4 py-3 transition-colors duration-150 hover:bg-foreground/5',
        previewed && 'lg:bg-primary/5 lg:shadow-[inset_3px_0_0_var(--color-primary)]',
      )}
      data-chart-id={chart.id}
      onMouseEnter={() => onPreview(chart.id, false)}
      onFocus={() => onPreview(chart.id, true)}
    >
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
        <p className="text-xs text-muted-foreground">{chartMeta(chart)}</p>
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
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [previewWidth, setPreviewWidth] = useState(() => loadPanelWidth(CHART_PREVIEW, browserStorage()))
  const hoverTimer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(hoverTimer.current), [])
  useEffect(() => savePanelWidth(CHART_PREVIEW, browserStorage(), previewWidth), [previewWidth])
  // Opening the list means a chart is likely next: load Plotly now, not after the click.
  useEffect(warmPlotly, [])

  const list = charts.data
  const ownDatasets = (datasets.data ?? []).filter((dataset) => dataset.kind === 'user')

  async function saveTitle(id: string, title: string) {
    await update.mutateAsync({ id, title })
    return true
  }

  // Hover waits; focus doesn't, so arrowing down the list keeps up with the keyboard.
  function preview(id: string, immediate: boolean) {
    window.clearTimeout(hoverTimer.current)
    if (immediate) setPreviewId(id)
    else hoverTimer.current = window.setTimeout(() => setPreviewId(id), HOVER_PREVIEW_DELAY_MS)
  }

  // Falls back to the first chart, so the panel is never empty and a deleted chart's preview goes away.
  const previewed = list?.find((chart) => chart.id === previewId) ?? list?.[0]

  return (
    <AppShell
      title="Charts"
      actions={
        <>
          <Button variant="ghost" size="sm" onClick={() => setNewDatasetOpen(true)}>
            New dataset
          </Button>
          <Button size="sm" asChild>
            <a href={newChartHref()}>
              <Plus aria-hidden />
              New chart
            </a>
          </Button>
        </>
      }
      status={list && `${plural(list.length, 'chart')} · ${plural(ownDatasets.length, 'dataset')} of your own`}
    >
      {/* The track is a variable so the two columns only exist from `lg` up, where the preview does. CSS clamps it
          too, so a remembered width still fits after the window shrinks; the handle clamps as it drags. */}
      <div
        className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_var(--preview-track)]"
        style={{ '--preview-track': panelTrack(CHART_PREVIEW, previewWidth) } as CSSProperties}
      >
        <div className="flex min-w-0 flex-col gap-6">
          {actionError && (
            <Alert variant="destructive" className="border-glass-border">
              <AlertDescription>{actionError}</AlertDescription>
            </Alert>
          )}

          {list === undefined ? (
            charts.isError ? (
              <p className="text-destructive">{charts.error.message}</p>
            ) : (
              <p className={cn('text-muted-foreground', delayedIn)}>Loading…</p>
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
                    previewed={chart.id === previewed?.id}
                    onPreview={preview}
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
                      className="own-dataset flex items-baseline gap-2 rounded-md px-2 py-1 transition-colors duration-150 hover:bg-foreground/5"
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
        </div>

        {/* Desktop only: the preview follows hover and focus, and is dragged wider, none of which a touch screen has. */}
        {previewed && (
          <div className="relative sticky top-0 hidden lg:block">
            {/* `inset`: the pane's own padding sits between this column and the window's right edge. */}
            <PanelResizeHandle
              limits={CHART_PREVIEW}
              width={previewWidth}
              onWidthChange={setPreviewWidth}
              label="Resize preview"
              inset={PANE_PADDING_PX}
            />
            <ChartPreview chart={previewed} width={previewWidth} />
          </div>
        )}
      </div>
    </AppShell>
  )
}
