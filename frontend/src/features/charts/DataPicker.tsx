import { Database } from 'lucide-react'
import type { DatasetSummary } from '@/api/client'
import { useAllDatasets } from '@/api/queries'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { datasetMeta, datasetSource } from '../data/datasetMeta'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPick: (datasetId: string) => void
}

/** Datasets grouped by their paper, papers alphabetically, "My data" last. */
function byPaper(datasets: DatasetSummary[]): [string, DatasetSummary[]][] {
  const groups = new Map<string, DatasetSummary[]>()
  for (const dataset of datasets) {
    const source = datasetSource(dataset)
    groups.set(source, [...(groups.get(source) ?? []), dataset])
  }
  const mine = datasetSource({ kind: 'user', paper_title: null })
  return [...groups].sort(([a], [b]) => Number(a === mine) - Number(b === mine) || a.localeCompare(b))
}

/** "Choose data": every dataset, searchable, grouped by paper. */
export function DataPicker({ open, onOpenChange, onPick }: Props) {
  const datasets = useAllDatasets()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-lg')}>
        <DialogHeader>
          <DialogTitle>Choose data</DialogTitle>
          <DialogDescription>Tables and numbers from your papers, and data of your own.</DialogDescription>
        </DialogHeader>
        <Command className="bg-transparent p-0">
          <CommandInput aria-label="Search data" placeholder="Search data…" />
          <CommandList>
            <CommandEmpty>
              {datasets.isPending
                ? 'Loading your data…'
                : datasets.isError
                  ? `Couldn't load your data: ${datasets.error.message}`
                  : datasets.data.length === 0
                    ? 'No data yet. Capture a table in a paper, or add data of your own on the Charts page.'
                    : 'No matching data.'}
            </CommandEmpty>
            {byPaper(datasets.data ?? []).map(([source, items]) => (
              <CommandGroup key={source} heading={source}>
                {items.map((dataset) => (
                  <CommandItem
                    key={dataset.id}
                    // The id keeps two datasets with the same name apart; the filter searches the keywords.
                    value={dataset.id}
                    keywords={[dataset.name, source]}
                    data-dataset-id={dataset.id}
                    onSelect={() => {
                      onPick(dataset.id)
                      onOpenChange(false)
                    }}
                  >
                    <span className="min-w-0 flex-1 truncate" title={dataset.name}>
                      {dataset.name}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{datasetMeta(dataset)}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  )
}

/** The "Data" field: the dataset in use, and a button to choose another. */
export function DataButton({ id, name, onClick }: { id: string; name: string | undefined; onClick: () => void }) {
  return (
    <div className="grid min-w-0 gap-1.5">
      <Label htmlFor={id}>Data</Label>
      <Button id={id} variant="outline" className="w-full min-w-0 justify-start" aria-label={`Data: ${name ?? 'loading'}`} onClick={onClick}>
        <Database aria-hidden />
        <span className="min-w-0 truncate" title={name}>
          {name ?? 'Loading…'}
        </span>
      </Button>
    </div>
  )
}
