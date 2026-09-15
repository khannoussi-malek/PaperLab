import { Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useDataset, useDatasetMutations } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { fadeIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { chartsHref, newChartHref, readerHref, type CellFocus } from '@/lib/route'
import { cn } from '@/lib/utils'
import { ChartsUsingDataDialog } from './ChartsUsingDataDialog'
import { datasetSource } from './datasetMeta'
import { chartsLosingColumns, fromDataset, type Grid, toGridIn } from './gridModel'
import { GridEditor } from './GridEditor'

type Props = { datasetId: string; focus: CellFocus | null }

const countedChart = (count: number) => `${count} chart${count === 1 ? '' : 's'} use${count === 1 ? 's' : ''}`

/** The owner's own copy of a dataset: rename it, fix its grid, delete it or start a chart from it. */
export function DatasetPage({ datasetId, focus }: Props) {
  const dataset = useDataset(datasetId)
  const { rename, saveGrid, remove } = useDatasetMutations()

  // The draft the editor works on. `savedRef` is the grid it matches when there are no unsaved edits (set on load
  // and again on a successful save), so `dirty` is a plain reference check instead of a deep comparison.
  const [draft, setDraft] = useState<Grid | null>(null)
  const savedRef = useRef<Grid | null>(null)
  const lastUpdatedAtRef = useRef<string | null>(null)
  const dirty = draft !== null && draft !== savedRef.current

  const [name, setName] = useState('')
  const [editingName, setEditingName] = useState(false)
  const [confirmLossOpen, setConfirmLossOpen] = useState(false)

  useEffect(() => {
    if (dataset.data) setName(dataset.data.name)
  }, [dataset.data?.name])

  // Re-initialise the draft from the server copy when it changes and the owner hasn't touched it yet; a dirty
  // draft is left alone so a background refetch never throws away unsaved edits.
  useEffect(() => {
    if (!dataset.data || dataset.data.updated_at === lastUpdatedAtRef.current || dirty) return
    const fresh = fromDataset(dataset.data)
    lastUpdatedAtRef.current = dataset.data.updated_at
    savedRef.current = fresh
    setDraft(fresh)
  }, [dataset.data, dirty])

  function save(force: boolean) {
    if (!draft || !dataset.data) return
    if (!force && chartsLosingColumns(dataset.data.charts, draft).length > 0) {
      setConfirmLossOpen(true)
      return
    }
    saveGrid.mutate(
      { id: datasetId, grid: toGridIn(draft), force },
      {
        onSuccess: (saved) => {
          const fresh = fromDataset(saved)
          lastUpdatedAtRef.current = saved.updated_at
          savedRef.current = fresh
          setDraft(fresh)
          setConfirmLossOpen(false)
        },
      },
    )
  }

  function commitName() {
    if (!dataset.data) return
    const trimmed = name.trim()
    if (!trimmed || trimmed === dataset.data.name) {
      setName(dataset.data.name)
      setEditingName(false)
      return
    }
    rename.mutate({ id: dataset.data.id, name: trimmed }, { onSuccess: () => setEditingName(false) })
  }

  const backHref = dataset.data?.paper_id ? readerHref(dataset.data.paper_id, 'data') : chartsHref

  function deleteDataset() {
    if (!dataset.data) return
    const count = dataset.data.charts.length
    const question =
      count > 0 ? `Delete this dataset? ${countedChart(count)} it and will lose that data.` : 'Delete this dataset?'
    if (!window.confirm(question)) return
    remove.mutate(
      { id: datasetId, force: count > 0 },
      {
        onSuccess: () => {
          window.location.hash = backHref
        },
      },
    )
  }

  const error = saveGrid.error ?? rename.error ?? remove.error

  if (dataset.isError) {
    return (
      <main className={cn('mx-auto flex max-w-5xl flex-col gap-4 px-4 py-6', fadeIn)}>
        <Button variant="ghost" size="sm" asChild className="-ml-2.5 self-start">
          <a href={chartsHref}>← Back</a>
        </Button>
        <p className="text-muted-foreground">This dataset doesn't exist.</p>
      </main>
    )
  }

  return (
    <main className={cn('mx-auto flex max-w-5xl flex-col gap-4 px-4 py-6 pb-24', fadeIn)}>
      <div>
        <Button variant="ghost" size="sm" asChild className="-ml-2.5">
          <a href={backHref}>← Back</a>
        </Button>
        {dataset.data && (
          <>
            {editingName ? (
              <Input
                autoFocus
                aria-label="Dataset name"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  rename.reset()
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') e.currentTarget.blur()
                  else if (e.key === 'Escape') {
                    setName(dataset.data!.name)
                    setEditingName(false)
                  }
                }}
                onBlur={commitName}
                className="mt-1 h-auto border-0 bg-transparent px-0 font-heading text-3xl font-semibold shadow-none focus-visible:ring-2"
              />
            ) : (
              <h1
                tabIndex={0}
                title="Rename"
                onClick={() => setEditingName(true)}
                onKeyDown={(e) => e.key === 'Enter' && setEditingName(true)}
                className="mt-1 cursor-text truncate rounded-md font-heading text-3xl font-semibold focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                {dataset.data.name}
              </h1>
            )}
            <p className="text-sm text-muted-foreground">
              {datasetSource(dataset.data)}
              {dataset.data.kind === 'table' && dataset.data.page !== null && ` · p. ${dataset.data.page}`}
            </p>
          </>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}

      {draft && <GridEditor grid={draft} onChange={setDraft} focus={focus} />}

      {dataset.data && (
        <>
          <div className="sticky bottom-0 -mx-4 mt-auto flex items-center justify-between gap-2 border-t border-glass-border bg-card/95 px-4 py-3 backdrop-blur">
            <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={deleteDataset} disabled={remove.isPending}>
              <Trash2 aria-hidden />
              Delete dataset
            </Button>
            <div className="flex gap-2">
              <Button variant="outline" asChild>
                <a href={newChartHref(dataset.data.id)}>Quick chart</a>
              </Button>
              <Button disabled={!dirty || saveGrid.isPending} onClick={() => save(false)}>
                {saveGrid.isPending ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </div>

          <ChartsUsingDataDialog
            open={confirmLossOpen}
            onOpenChange={setConfirmLossOpen}
            charts={draft ? chartsLosingColumns(dataset.data.charts, draft) : []}
            pending={saveGrid.isPending}
            onConfirm={() => save(true)}
          />
        </>
      )}
    </main>
  )
}
