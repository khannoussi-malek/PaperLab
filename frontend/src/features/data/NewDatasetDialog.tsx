import { useEffect, useState, type FormEvent } from 'react'
import { useDatasetMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { datasetHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { emptyGrid, toGridIn } from './gridModel'

const MIN_COLUMNS = 1
const MAX_COLUMNS = 50
const DEFAULT_COLUMNS = 2

type Tab = 'type' | 'paste' | 'upload'

type Props = { open: boolean; onOpenChange: (open: boolean) => void }

const clampColumns = (n: number) => Math.min(MAX_COLUMNS, Math.max(MIN_COLUMNS, Number.isFinite(n) ? Math.trunc(n) : DEFAULT_COLUMNS))

function readyToCreate(name: string, tab: Tab, pasted: string, csvFile: File | null): boolean {
  if (!name.trim()) return false
  if (tab === 'upload') return csvFile !== null
  if (tab === 'paste') return pasted.trim() !== ''
  return true
}

/** "Dataset name" plus Type / Paste / Upload CSV: every way to start a dataset of your own. Opens the new dataset's page. */
export function NewDatasetDialog({ open, onOpenChange }: Props) {
  const { create, importFile } = useDatasetMutations()
  const [tab, setTab] = useState<Tab>('type')
  const [name, setName] = useState('')
  const [columns, setColumns] = useState(DEFAULT_COLUMNS)
  const [pasted, setPasted] = useState('')
  const [csvFile, setCsvFile] = useState<File | null>(null)

  // A fresh form each time the dialog opens.
  useEffect(() => {
    if (!open) return
    setTab('type')
    setName('')
    setColumns(DEFAULT_COLUMNS)
    setPasted('')
    setCsvFile(null)
    create.reset()
    importFile.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const trimmedName = name.trim()
    try {
      if (tab === 'type') {
        const names = Array.from({ length: columns }, (_, i) => `Column ${i + 1}`)
        const dataset = await create.mutateAsync({ name: trimmedName, kind: 'user', grid: toGridIn(emptyGrid(names, 3)) })
        window.location.hash = datasetHref(dataset.id)
        return
      }
      const file = tab === 'paste' ? new File([pasted], 'pasted.csv', { type: 'text/csv' }) : csvFile
      if (!file) return
      const dataset = await importFile.mutateAsync({ file, name: trimmedName })
      window.location.hash = datasetHref(dataset.id)
    } catch {
      // shown in the alert below from create.error / importFile.error
    }
  }

  const pending = create.isPending || importFile.isPending
  const error = create.error ?? importFile.error

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-lg')}>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>New dataset</DialogTitle>
          </DialogHeader>

          <div className="grid gap-1.5">
            <Label htmlFor="new-dataset-name">Dataset name</Label>
            <Input id="new-dataset-name" autoFocus required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
          </div>

          <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)}>
            <TabsList>
              <TabsTrigger value="type">Type</TabsTrigger>
              <TabsTrigger value="paste">Paste</TabsTrigger>
              <TabsTrigger value="upload">Upload CSV</TabsTrigger>
            </TabsList>
            <TabsContent value="type" className="grid gap-1.5">
              <Label htmlFor="new-dataset-columns">Columns</Label>
              <Input
                id="new-dataset-columns"
                type="number"
                className="w-24 tabular-nums"
                min={MIN_COLUMNS}
                max={MAX_COLUMNS}
                value={columns}
                onChange={(e) => setColumns(clampColumns(Number(e.target.value)))}
              />
            </TabsContent>
            <TabsContent value="paste" className="grid gap-1.5">
              <Label htmlFor="new-dataset-pasted">Pasted data</Label>
              <Textarea
                id="new-dataset-pasted"
                rows={6}
                placeholder={'model\tscore\nA\t1.5\nB\t2.5'}
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
              />
            </TabsContent>
            <TabsContent value="upload" className="grid gap-1.5">
              <Label htmlFor="new-dataset-csv">CSV file</Label>
              <Input
                id="new-dataset-csv"
                type="file"
                accept=".csv,text/csv"
                aria-label="CSV file"
                onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
              />
            </TabsContent>
          </Tabs>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          )}

          <DialogFooter className="bg-transparent">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!readyToCreate(name, tab, pasted, csvFile) || pending}>
              {pending ? 'Creating…' : 'Create dataset'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
