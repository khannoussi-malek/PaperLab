import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, type Dataset } from '@/api/client'
import { useDatasetMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { PdfRect } from '../reader/coords'
import type { PDFDocumentProxy, PDFPageProxy } from '../reader/pdfjs'
import { fromPreview, type Grid, toGridIn } from './gridModel'
import { GridEditor } from './GridEditor'

type Props = {
  paperId: string
  doc: PDFDocumentProxy
  page: number
  region: PdfRect
  onClose: () => void
  onSaved: (dataset: Dataset) => void
}

const CROP_SCALE = 2

/** The dragged region of the page, drawn by PDF.js at 2× so the owner can check the grid against it. */
function CaptureCrop({ doc, page, region }: Pick<Props, 'doc' | 'page' | 'region'>) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [x0, y0, x1, y1] = region

  useEffect(() => {
    const canvas = canvasRef.current!
    let active = true
    let task: ReturnType<PDFPageProxy['render']> | null = null
    doc
      .getPage(page)
      .then((pdfPage) => {
        if (!active) return
        task = pdfPage.render({
          canvas,
          viewport: pdfPage.getViewport({ scale: 1 }),
          transform: [CROP_SCALE, 0, 0, CROP_SCALE, -CROP_SCALE * x0, -CROP_SCALE * y0],
        })
        return task.promise
      })
      .catch((error: Error) => {
        if (error.name !== 'RenderingCancelledException') console.error(`crop of page ${page}`, error)
      })
    return () => {
      active = false
      task?.cancel()
    }
  }, [doc, page, x0, y0])

  return (
    // The paper stays white in both themes.
    <div className="self-start overflow-auto rounded-lg bg-white ring-1 ring-glass-border">
      <canvas
        ref={canvasRef}
        className="capture-crop h-auto max-w-full"
        aria-label={`Page ${page}, the captured region`}
        width={Math.ceil((x1 - x0) * CROP_SCALE)}
        height={Math.ceil((y1 - y0) * CROP_SCALE)}
        style={{ width: x1 - x0 }}
      />
    </div>
  )
}

/** Reads the table in a dragged region, lets the owner fix its name and grid next to the crop, and saves it. */
export function CaptureTableDialog({ paperId, doc, page, region, onClose, onSaved }: Props) {
  const { create } = useDatasetMutations()
  const [attempt, setAttempt] = useState(0)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [grid, setGrid] = useState<Grid | null>(null)

  useEffect(() => {
    let active = true
    api.previewTable(paperId, page, region).then(
      (preview) => {
        if (!active) return
        setName(preview.name ?? '')
        setGrid(fromPreview(preview))
      },
      (error: Error) => active && setPreviewError(error.message),
    )
    return () => {
      active = false
    }
  }, [paperId, page, region, attempt])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!grid) return
    try {
      const dataset = await create.mutateAsync({ name: name.trim(), kind: 'table', paper_id: paperId, page, region, grid: toGridIn(grid) })
      onSaved(dataset)
    } catch {
      // shown in the alert above the footer from create.error
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className={cn(glass, 'max-h-[calc(100dvh-2rem)] overflow-y-auto bg-glass-strong ring-glass-border sm:max-w-5xl')}>
        <form onSubmit={save} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Capture table</DialogTitle>
            <DialogDescription>Check the grid against the page, fix anything read wrong, then save it.</DialogDescription>
          </DialogHeader>

          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <CaptureCrop doc={doc} page={page} region={region} />
            <div className="grid min-h-40 content-start gap-4">
              {previewError && (
                <Alert variant="destructive">
                  <AlertDescription className="flex items-center justify-between gap-2">
                    {previewError}
                    <Button type="button" variant="outline" size="sm" onClick={() => {
                        setPreviewError(null)
                        setAttempt((n) => n + 1)
                      }}>
                      Try again
                    </Button>
                  </AlertDescription>
                </Alert>
              )}
              {!grid && !previewError && (
                <p role="status" className="text-sm text-muted-foreground">
                  Reading the table…
                </p>
              )}
              {grid && (
                <>
                  <div className="grid gap-1.5">
                    <Label htmlFor="capture-table-name">Table name</Label>
                    <Input id="capture-table-name" autoFocus required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
                  </div>
                  <GridEditor grid={grid} onChange={setGrid} />
                </>
              )}
            </div>
          </div>

          {create.error && (
            <Alert variant="destructive">
              <AlertDescription>{create.error.message}</AlertDescription>
            </Alert>
          )}
          <DialogFooter className="bg-transparent">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!grid || name.trim() === '' || create.isPending}>
              {create.isPending ? 'Saving…' : 'Save table'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
