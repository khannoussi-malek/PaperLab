import { ChartColumn, Crosshair, Hash, Table2 } from 'lucide-react'
import type { DatasetSummary } from '@/api/client'
import { usePaperDatasets } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { datasetHref, newChartHref } from '@/lib/route'
import type { PdfRect } from '../reader/coords'
import { datasetMeta } from './datasetMeta'

type Props = {
  paperId: string
  /** Scrolls the reader to a page and flashes the rects there. */
  onShowRegion: (page: number, rects: PdfRect[]) => void
}

function DatasetIcon({ kind }: { kind: DatasetSummary['kind'] }) {
  const Icon = kind === 'numbers' ? Hash : Table2
  return <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
}

/** The Data tab: the tables captured from this paper and the numbers picked from its text. */
export function DataPanel({ paperId, onShowRegion }: Props) {
  const datasets = usePaperDatasets(paperId)
  return (
    // RightPanel draws the glass and the border, as for Notes.
    <aside className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4" aria-label="Data">
      {datasets.error && (
        <Alert variant="destructive">
          <AlertDescription>{datasets.error.message}</AlertDescription>
        </Alert>
      )}
      {datasets.data?.length === 0 && (
        <div className="grid place-items-center gap-2 rounded-xl border border-dashed border-glass-border px-4 py-10 text-center">
          <Table2 aria-hidden className="size-6 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">No data from this paper yet.</p>
        </div>
      )}
      <ul aria-label="Datasets" className="flex flex-col gap-2">
        {datasets.data?.map((dataset) => (
          <li key={dataset.id}>
            <article className="dataset-card" data-dataset-id={dataset.id}>
              <Card size="sm" className="bg-glass-strong ring-glass-border">
                <CardHeader className="flex items-center gap-2">
                  <DatasetIcon kind={dataset.kind} />
                  <h3 className="truncate font-medium" title={dataset.name}>
                    {dataset.name}
                  </h3>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground tabular-nums">{datasetMeta(dataset)}</CardContent>
                <CardFooter className="justify-end gap-2">
                  {dataset.page !== null && dataset.region !== null && (
                    <Button variant="ghost" size="sm" onClick={() => onShowRegion(dataset.page!, [dataset.region!])}>
                      <Crosshair aria-hidden />
                      Show in paper
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" asChild>
                    <a href={datasetHref(dataset.id)}>Open</a>
                  </Button>
                  <Button variant="ghost" size="sm" asChild>
                    <a href={newChartHref(dataset.id)}>
                      <ChartColumn aria-hidden />
                      Quick chart
                    </a>
                  </Button>
                </CardFooter>
              </Card>
            </article>
          </li>
        ))}
      </ul>
    </aside>
  )
}
