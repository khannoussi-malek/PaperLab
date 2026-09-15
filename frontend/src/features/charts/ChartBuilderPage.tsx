import { Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ChartSpec, Dataset, SeriesSpec } from '@/api/client'
import { useChart, useChartMutations, useDataset, useLoadDataset } from '@/api/queries'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { ModeToggle } from '@/components/mode-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { chartHref, chartsHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { AxesFields } from './AxesFields'
import { changeType, copyTitle, isSeriesType, newSeries, panelProblem, quickChartSpec, specDatasetIds, type ChartType } from './builderSpec'
import { ChartTypePicker } from './ChartTypePicker'
import { ChartView } from './ChartView'
import { DataButton, DataPicker } from './DataPicker'
import { GridChartFields } from './GridChartFields'
import { Field, SeriesEditor } from './SeriesEditor'

type Props = { chartId: string | null; datasetId: string | null }

const PREVIEW_DELAY_MS = 300

/** A series editor with its own dataset loaded (cached, so each dataset loads once however many series read it). */
function LoadedSeriesEditor(props: Omit<Parameters<typeof SeriesEditor>[0], 'dataset'>) {
  const dataset = useDataset(props.series.dataset_id)
  return <SeriesEditor {...props} dataset={dataset.data} />
}

/** The spec after picking data: a series appended, or a grid chart (re)built from the dataset. */
function withData(spec: ChartSpec | null, type: ChartType, dataset: Dataset): ChartSpec | null {
  if (spec && !('series' in spec)) return changeType(null, spec.type, dataset)
  if (!isSeriesType(type) && !spec) return changeType(null, type, dataset)
  const series = newSeries(dataset, spec?.series ?? [])
  if (!series) return null
  if (spec) return { ...spec, series: [...spec.series, series] }
  return isSeriesType(type) ? { version: 1, type, series: [series] } : null
}

const notesLine = (count: number) => `Used in ${count} note${count === 1 ? '' : 's'}, which will show this change`

/** Builds a new chart (empty, or a quick chart of one dataset) or edits a saved one, with a live preview. */
export function ChartBuilderPage({ chartId, datasetId }: Props) {
  const chart = useChart(chartId)
  const quick = useDataset(datasetId)
  const { create, update } = useChartMutations()
  const loadDataset = useLoadDataset()
  const [spec, setSpec] = useState<ChartSpec | null>(null)
  const [title, setTitle] = useState('')
  const [type, setType] = useState<ChartType>('bar')
  const [started, setStarted] = useState(chartId === null && datasetId === null)
  const [picking, setPicking] = useState(false)
  const [pickError, setPickError] = useState<string | null>(null)
  const [preview, setPreview] = useState<ChartSpec | null>(null)
  const firstDataset = useDataset(specDatasetIds(spec)[0] ?? null).data ?? null
  // A pick applies after its dataset loads, by which time the chart may have changed: it reads the latest type here
  // and updates the spec through `setSpec`'s updater, never the copy its render saw.
  const latest = useRef({ spec, type })
  useEffect(() => {
    latest.current = { spec, type }
  })

  // The starting point, once it has loaded: the saved chart, or a quick chart of the dataset.
  if (!started && chart.data) {
    setStarted(true)
    setSpec(chart.data.spec)
    setPreview(chart.data.spec)
    setTitle(chart.data.title)
    setType(chart.data.spec.type)
  } else if (!started && quick.data) {
    setStarted(true)
    setSpec(quickChartSpec(quick.data))
    setPreview(quickChartSpec(quick.data))
    setTitle(quick.data.name)
  }

  useEffect(() => {
    const timer = window.setTimeout(() => setPreview(spec), PREVIEW_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [spec])

  function chooseType(next: ChartType) {
    setType(next)
    if (spec) setSpec(changeType(spec, next, firstDataset) ?? spec)
  }

  /** "Add series" on a series chart (or no chart yet); "Change data" on a grid chart. */
  function applyData(dataset: Dataset) {
    const { spec: committed, type: currentType } = latest.current
    if (!withData(committed, currentType, dataset)) return setPickError(`“${dataset.name}” doesn't have the columns this chart needs.`)
    setSpec((current) => withData(current, currentType, dataset) ?? current)
  }

  /** Series change and go by id: a series card's data can finish loading after other series were added or removed. */
  function updateSeries(change: (series: SeriesSpec[]) => SeriesSpec[]) {
    setSpec((current) => {
      if (!current || !('series' in current)) return current
      const series = change(current.series)
      return series.length > 0 ? { ...current, series } : null
    })
  }

  async function pick(id: string) {
    setPickError(null)
    try {
      applyData(await loadDataset(id))
    } catch (error) {
      setPickError(error instanceof Error ? error.message : String(error))
    }
  }

  async function save(asCopy: boolean) {
    if (!spec) return
    create.reset()
    update.reset()
    const name = title.trim()
    try {
      if (chartId && !asCopy) {
        await update.mutateAsync({ id: chartId, title: name, spec })
        window.location.hash = chartHref(chartId)
      } else {
        const created = await create.mutateAsync({ title: asCopy ? copyTitle(name) : name, spec })
        window.location.hash = chartHref(created.id)
      }
    } catch {
      // Shown in the alert above the footer.
    }
  }

  // A failed background refetch keeps what already loaded: only a load that never succeeded is an error here.
  const loadError = (chart.data ? null : chart.error) ?? (quick.data ? null : quick.error)
  const problem = spec ? panelProblem(spec) : null
  const saving = create.isPending || update.isPending
  const saveError = create.error ?? update.error
  const canSave = spec !== null && problem === null && title.trim() !== '' && !saving
  const noteCount = chart.data?.note_ids.length ?? 0

  return (
    <main className={cn('mx-auto flex max-w-7xl flex-col gap-4 px-4 py-6', fadeIn)}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Button variant="ghost" size="sm" asChild className="-ml-2.5">
            <a href={chartId ? chartHref(chartId) : chartsHref}>{chartId ? '← Chart' : '← Charts'}</a>
          </Button>
          <h1 className="mt-1 font-heading text-3xl font-semibold">{chartId ? 'Edit chart' : 'New chart'}</h1>
        </div>
        <ModeToggle />
      </header>

      {loadError && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{chartId ? "This chart doesn't exist." : `Couldn't load that data: ${loadError.message}`}</AlertDescription>
        </Alert>
      )}

      {!started && !loadError && <p className="text-sm text-muted-foreground">Loading…</p>}

      {started && (
        <div className="grid items-start gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
          <Card className={cn('min-w-0 ring-glass-border', glass)}>
            <CardContent className="flex flex-col gap-5">
              <section className="grid gap-2">
                <h2 className="text-sm font-medium">Chart type</h2>
                <ChartTypePicker value={type} enabled={(t) => !spec || changeType(spec, t, firstDataset) !== null} onChange={chooseType} />
              </section>

              <section className="grid gap-3">
                {spec && !('series' in spec) ? (
                  <>
                    <DataButton id="grid-data" name={firstDataset?.name} onClick={() => setPicking(true)} />
                    <GridChartFields spec={spec} dataset={firstDataset ?? undefined} onChange={setSpec} />
                  </>
                ) : (
                  <>
                    <h2 className="text-sm font-medium">Series</h2>
                    {spec?.series.map((series, i) => (
                      <LoadedSeriesEditor
                        key={series.id}
                        series={series}
                        index={i}
                        type={spec.type}
                        facet={spec.layout?.facet === 'series'}
                        onChange={(next) => updateSeries((all) => all.map((s) => (s.id === next.id ? next : s)))}
                        onRemove={() => updateSeries((all) => all.filter((s) => s.id !== series.id))}
                      />
                    ))}
                    <Button variant="ghost" className="justify-self-start" onClick={() => setPicking(true)}>
                      <Plus aria-hidden />
                      {isSeriesType(type) ? 'Add series' : 'Choose data'}
                    </Button>
                  </>
                )}
                {pickError && (
                  <p role="alert" className="text-xs text-destructive">
                    {pickError}
                  </p>
                )}
                <DataPicker open={picking} onOpenChange={setPicking} onPick={(id) => void pick(id)} />
              </section>

              {spec && <AxesFields spec={spec} onChange={setSpec} />}

              <Field id="chart-title" label="Chart title">
                <Input id="chart-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
              </Field>

              {saveError && (
                <Alert variant="destructive" className="border-glass-border">
                  <AlertDescription>{saveError.message}</AlertDescription>
                </Alert>
              )}
              <footer className="flex flex-col gap-2">
                <div className="flex flex-wrap gap-2">
                  {chartId ? (
                    <>
                      <Button disabled={!canSave} onClick={() => void save(false)}>
                        Save changes
                      </Button>
                      <Button variant="outline" disabled={!canSave} onClick={() => void save(true)}>
                        Save as copy
                      </Button>
                    </>
                  ) : (
                    <Button disabled={!canSave} onClick={() => void save(false)}>
                      Save chart
                    </Button>
                  )}
                </div>
                {chartId && noteCount > 0 && <p className="text-sm text-muted-foreground">{notesLine(noteCount)}</p>}
                {problem && (
                  <p role="status" className="text-sm text-destructive">
                    {problem}
                  </p>
                )}
              </footer>
            </CardContent>
          </Card>

          <Card className={cn('min-w-0 ring-glass-border lg:sticky lg:top-4', glass)}>
            <CardContent>
              {preview ? (
                <ChartView spec={preview} />
              ) : (
                <p className="grid min-h-90 place-items-center text-sm text-muted-foreground">Add a series to start the chart.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </main>
  )
}
