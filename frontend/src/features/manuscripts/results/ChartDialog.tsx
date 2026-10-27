import { useMemo, useRef, useState } from 'react'
import { useChart, useCharts, useResolvedChart, useUploadManuscriptFile } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { loadPlotly } from '@/features/charts/loadPlotly'
import { ChartView } from '@/features/charts/ChartView'
import { latexEscape } from '../deck/latex'
import { slug, uniqueLabel } from './insertBlock'
import { pgfplotsSupport, toPgfplots } from './pgfplots'
import type { InsertResult } from './useInsertBlock'

const PNG_WIDTH = 1950 // 6.5 inches at 300 dpi
const FALLBACK_ASPECT = 0.6

const dataUrlToFile = (url: string, name: string): File => {
  const bytes = Uint8Array.from(atob(url.slice(url.indexOf(',') + 1)), (c) => c.charCodeAt(0))
  return new File([bytes], name, { type: 'image/png' })
}

/** `figures/<slug>.png`, or `-2`, `-3`... when the manuscript already has that file. */
function uniquePath(files: string[], base: string): string {
  const used = new Set(files)
  let n = 1
  while (used.has(`figures/${n === 1 ? base : `${base}-${n}`}.png`)) n++
  return `figures/${n === 1 ? base : `${base}-${n}`}.png`
}

const figure = (body: string, caption: string, label: string) =>
  `\\begin{figure}[htbp]\n\\centering\n${body}\n\\caption{${caption}}\n\\label{${label}}\n\\end{figure}`

/** Inserts a saved chart: pgfplots when it can be drawn in LaTeX, else a PNG picture uploaded to the manuscript. */
export function ChartDialog({ open, onOpenChange, manuscriptId, labelTexts, filePaths, onInsert, onClosed }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  manuscriptId: string
  labelTexts: () => string[]
  filePaths: () => string[]
  onInsert: (code: string, packages: string[]) => Promise<InsertResult>
  onClosed?: (inserted: boolean) => void
}) {
  const inserted = useRef(false)
  const preview = useRef<HTMLDivElement>(null)
  const charts = useCharts()
  const upload = useUploadManuscriptFile()
  const [chartId, setChartId] = useState<string | null>(null)
  const chart = useChart(chartId)
  const spec = chart.data?.spec ?? null
  const resolved = useResolvedChart(spec)
  const [caption, setCaption] = useState<string | null>(null)
  const [label, setLabel] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const title = chart.data?.title ?? ''
  const shownCaption = caption ?? title
  const shownLabel = label ?? uniqueLabel(labelTexts(), `fig:${slug(title || 'chart')}`)
  const ready = resolved.data && !resolved.isPlaceholderData ? resolved.data : null
  const support = useMemo(() => (ready ? pgfplotsSupport(ready.spec, ready.data) : null), [ready])
  const latex = useMemo(() => {
    if (!ready || !support?.ok) return null
    try {
      return toPgfplots(ready.spec, ready.data, { caption: latexEscape(shownCaption), label: shownLabel.trim() })
    } catch (e) {
      return e instanceof Error ? e.message : String(e)
    }
  }, [ready, support, shownCaption, shownLabel])

  const finish = (result: InsertResult) => {
    if (result.ok) {
      inserted.current = true
      onOpenChange(false)
      return true
    }
    setError(result.message)
    return false
  }

  const insertPgfplots = async () => {
    if (!latex || !support?.ok) return
    setBusy(true)
    setError(null)
    try {
      finish(await onInsert(latex, ['pgfplots']))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const insertPicture = async () => {
    const graph = preview.current?.querySelector<HTMLElement>('.js-plotly-plot')
    if (!graph) return setError("The chart isn't drawn yet.")
    setBusy(true)
    setError(null)
    let path = ''
    try {
      const Plotly = await loadPlotly()
      const aspect = graph.clientWidth ? graph.clientHeight / graph.clientWidth : FALLBACK_ASPECT
      const url = await Plotly.toImage(graph as never, { format: 'png', width: PNG_WIDTH, height: Math.round(PNG_WIDTH * (aspect || FALLBACK_ASPECT)), scale: 1 })
      path = uniquePath(filePaths(), slug(title || 'chart'))
      await upload.mutateAsync({ id: manuscriptId, path, file: dataUrlToFile(url, path.slice(path.lastIndexOf('/') + 1)) })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
      return
    }
    try {
      const code = figure(`\\includegraphics[width=\\linewidth]{${path.replace(/\.png$/, '')}}`, latexEscape(shownCaption), shownLabel.trim())
      const result = await onInsert(code, ['graphicx'])
      if (!result.ok) setError(`${result.message} The picture was saved as ${path}; insert it again.`)
      else finish(result)
    } catch (e) {
      setError(`${e instanceof Error ? e.message : String(e)} The picture was saved as ${path}; insert it again.`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl" onCloseAutoFocus={(e) => { e.preventDefault(); onClosed?.(inserted.current) }}>
        <DialogHeader>
          <DialogTitle>Insert a chart</DialogTitle>
          <DialogDescription>A saved chart, as a pgfplots figure or a picture at your cursor.</DialogDescription>
        </DialogHeader>
        <Command className="h-40 border">
          <CommandInput placeholder="Search charts…" />
          <CommandList>
            <CommandEmpty>{charts.isError ? "Couldn't load your charts." : 'No charts found.'}</CommandEmpty>
            {(charts.data ?? []).map((c) => (
              <CommandItem key={c.id} value={`${c.title} ${c.id}`} data-checked={c.id === chartId} onSelect={() => { setChartId(c.id); setCaption(null); setLabel(null); setError(null) }}>
                {c.title}<span className="ml-2 text-xs text-muted-foreground">{c.type}</span>
              </CommandItem>
            ))}
          </CommandList>
        </Command>
        {chart.isError && <p className="text-sm text-destructive">Couldn't load that chart.</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">Caption
            <Input value={shownCaption} onChange={(e) => setCaption(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm">Label
            <Input value={shownLabel} onChange={(e) => setLabel(e.target.value)} />
          </label>
        </div>
        {support && !support.ok && <p role="status" className="text-sm text-muted-foreground">{support.reason}</p>}
        {support?.ok && support.notes.map((n) => <p key={n} role="status" className="text-sm text-muted-foreground">{n}</p>)}
        <Tabs defaultValue="chart">
          <TabsList>
            <TabsTrigger value="chart">Chart</TabsTrigger>
            <TabsTrigger value="latex" disabled={!support?.ok}>LaTeX</TabsTrigger>
          </TabsList>
          <TabsContent value="chart" forceMount className="data-[state=inactive]:hidden">
            <div ref={preview}>{spec ? <ChartView spec={spec} height={260} staticPlot withTable={false} /> : <p className="text-sm text-muted-foreground">Pick a chart to preview it.</p>}</div>
          </TabsContent>
          <TabsContent value="latex">
            {latex && <pre className="max-h-60 overflow-auto rounded-lg border border-glass-border p-2 text-xs">{latex}</pre>}
          </TabsContent>
        </Tabs>
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          {support && !support.ok
            ? <Button type="button" disabled={busy} onClick={() => void insertPicture()}>Insert as a picture</Button>
            : <Button type="button" disabled={busy || !support?.ok} onClick={() => void insertPgfplots()}>Insert</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
