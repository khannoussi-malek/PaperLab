import { useMemo, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import { useAllDatasets, useDataset, usePinPaper } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { latexEscape } from '../deck/latex'
import { slug, uniqueLabel } from './insertBlock'
import { datasetToTable, parsePasted, toBooktabs, type TableInput } from './table'
import type { InsertResult } from './useInsertBlock'

const SELECT = 'h-8 rounded-lg border border-input bg-transparent px-2 text-sm'
const BEST = [['none', 'No bold'], ['max', 'Bold the highest'], ['min', 'Bold the lowest']] as const

function Preview({ table }: { table: TableInput }) {
  return (
    <div className="max-h-60 overflow-auto rounded-lg border border-glass-border">
      <table className="w-full text-sm">
        <thead><tr>{table.headers.map((h, i) => <th key={i} className="border-b px-2 py-1 text-left font-medium">{h}</th>)}</tr></thead>
        <tbody>
          {table.rows.map((r, i) => <tr key={i}>{table.headers.map((_, c) => <td key={c} className="px-2 py-1">{r[c]?.raw ?? ''}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  )
}

/** Inserts a table from a saved dataset or a paste, as a booktabs `table` at the cursor. */
export function TableDialog({ open, onOpenChange, manuscriptId, labelTexts, onInsert, onClosed }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  manuscriptId: string
  labelTexts: () => string[]
  onInsert: (code: string, packages: string[]) => Promise<InsertResult>
  /** After the dialog closes, who gets focus back: the caller decides (the editor after an insert, else the Insert button). */
  onClosed?: (inserted: boolean) => void
}) {
  const inserted = useRef(false)
  const datasets = useAllDatasets()
  const pin = usePinPaper()
  const [source, setSource] = useState<'dataset' | 'paste'>('dataset')
  const [datasetId, setDatasetId] = useState<string | null>(null)
  const detail = useDataset(datasetId)
  const [pasted, setPasted] = useState('')
  const [decimals, setDecimals] = useState('none')
  const [best, setBest] = useState<'none' | 'max' | 'min'>('none')
  const [caption, setCaption] = useState<string | null>(null)
  const [label, setLabel] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const table = useMemo<TableInput | null>(() => {
    if (source === 'paste') return pasted.trim() ? parsePasted(pasted) : null
    return detail.data ? datasetToTable(detail.data) : null
  }, [source, pasted, detail.data])
  const name = source === 'dataset' ? detail.data?.name ?? '' : ''
  const shownCaption = caption ?? name
  const shownLabel = label ?? uniqueLabel(labelTexts(), `tab:${slug(name || 'table')}`)
  const sourceNote = (cite: string) => (table?.source ? ` Source: ${cite}` : '')
  const build = (cite: string): { code: string } | { problem: string } => {
    if (!table) return { problem: '' }
    try {
      return { code: toBooktabs(table, { decimals: decimals === 'none' ? null : Number(decimals), best, caption: latexEscape(shownCaption) + sourceNote(cite), label: shownLabel.trim() }) }
    } catch (e) {
      return { problem: e instanceof Error ? e.message : String(e) }
    }
  }
  const preview = build('\\citep{key}')

  const insert = async () => {
    if (!table) return
    setBusy(true)
    setError(null)
    try {
      let cite = ''
      if (table.source) {
        try {
          cite = `\\citep{${(await pin.mutateAsync({ id: manuscriptId, paperId: table.source.paperId })).key}}`
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 404)) throw e
          cite = latexEscape(table.source.paperTitle) // not citable for this manuscript: name the paper, pin nothing
        }
      }
      const built = build(cite)
      if (!('code' in built)) return setError(built.problem)
      const result = await onInsert(built.code, ['booktabs'])
      if (result.ok) {
        inserted.current = true
        onOpenChange(false)
      }
      else setError(result.message)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl" onCloseAutoFocus={(e) => { e.preventDefault(); onClosed?.(inserted.current) }}>
        <DialogHeader>
          <DialogTitle>Insert a table</DialogTitle>
          <DialogDescription>From a saved dataset or a paste, as a booktabs table at your cursor.</DialogDescription>
        </DialogHeader>
        <Tabs value={source} onValueChange={(v) => setSource(v as 'dataset' | 'paste')}>
          <TabsList>
            <TabsTrigger value="dataset">Saved dataset</TabsTrigger>
            <TabsTrigger value="paste">Paste</TabsTrigger>
          </TabsList>
          <TabsContent value="dataset">
            <Command className="h-48 border">
              <CommandInput placeholder="Search datasets…" />
              <CommandList>
                <CommandEmpty>{datasets.isError ? "Couldn't load your datasets." : 'No datasets found.'}</CommandEmpty>
                {(datasets.data ?? []).map((d) => (
                  <CommandItem key={d.id} value={`${d.name} ${d.id}`} data-checked={d.id === datasetId} onSelect={() => { setDatasetId(d.id); setCaption(null); setLabel(null) }}>
                    {d.name}{d.paper_title && <span className="ml-2 truncate text-xs text-muted-foreground">{d.paper_title}</span>}
                  </CommandItem>
                ))}
              </CommandList>
            </Command>
            {detail.isError && <p className="mt-2 text-sm text-destructive">Couldn't load that dataset.</p>}
          </TabsContent>
          <TabsContent value="paste">
            <Textarea aria-label="Paste a table" rows={6} value={pasted} onChange={(e) => setPasted(e.target.value)} placeholder="Paste from Excel, Sheets or a CSV. The first row is the header." />
          </TabsContent>
        </Tabs>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">Decimal places
            <select className={SELECT} value={decimals} onChange={(e) => setDecimals(e.target.value)}>
              <option value="none">As written</option>
              {[0, 1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">Best value
            <select className={SELECT} value={best} onChange={(e) => setBest(e.target.value as typeof best)}>
              {BEST.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">Caption
            <Input value={shownCaption} onChange={(e) => setCaption(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm">Label
            <Input value={shownLabel} onChange={(e) => setLabel(e.target.value)} />
          </label>
        </div>
        {table?.source && <p className="text-xs text-muted-foreground">The caption ends with the source paper, cited once you insert.</p>}
        <Tabs defaultValue="table">
          <TabsList>
            <TabsTrigger value="table">Table</TabsTrigger>
            <TabsTrigger value="latex">LaTeX</TabsTrigger>
          </TabsList>
          <TabsContent value="table">{table ? <Preview table={table} /> : <p className="text-sm text-muted-foreground">Pick a dataset or paste a table to preview it.</p>}</TabsContent>
          <TabsContent value="latex">
            {'code' in preview ? <pre className="max-h-60 overflow-auto rounded-lg border border-glass-border p-2 text-xs">{preview.code}</pre> : <p className="text-sm text-destructive">{preview.problem}</p>}
          </TabsContent>
        </Tabs>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="button" disabled={busy || !('code' in preview)} onClick={() => void insert()}>Insert</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
