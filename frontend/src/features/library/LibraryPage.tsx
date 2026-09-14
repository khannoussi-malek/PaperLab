import { FileText, LoaderCircle, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Paper } from '@/api/client'
import { useDeletePaper, usePapers, useUploadPapers } from '@/api/queries'
import { glass } from '@/components/glass'
import { ModeToggle } from '@/components/mode-toggle'
import { fadeIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { readerHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { PaperPreview } from './PaperPreview'
import { byline, pageCountLabel } from './paperMeta'

/** Skimming the list with the mouse shouldn't open a PDF for every row it crosses. */
const HOVER_PREVIEW_DELAY_MS = 150

const isIngesting = (paper: Paper) => paper.status !== 'ready' && paper.status !== 'failed'

type RowProps = {
  paper: Paper
  previewed: boolean
  onPreview: (id: string, immediate: boolean) => void
  onDelete: (paper: Paper) => void
}

function PaperRow({ paper, previewed, onPreview, onDelete }: RowProps) {
  const meta = [byline(paper), pageCountLabel(paper.page_count)].filter(Boolean).join(' · ')
  return (
    <li
      className={cn(
        'paper-row group relative flex items-start gap-3 px-4 py-3 transition-colors duration-150 hover:bg-foreground/5',
        previewed && 'lg:bg-primary/5 lg:shadow-[inset_3px_0_0_var(--color-primary)]',
      )}
      onMouseEnter={() => onPreview(paper.id, false)}
      onFocus={() => onPreview(paper.id, true)}
    >
      <FileText aria-hidden className="mt-1 size-4 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        {/* The link's ::after covers the row, so the whole row opens the reader. */}
        <a
          href={readerHref(paper.id)}
          title={paper.title}
          className="line-clamp-2 rounded-sm font-heading wrap-anywhere text-lg leading-snug font-semibold outline-none after:absolute after:inset-0 focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {paper.title}
        </a>
        {meta && <p className="mt-0.5 truncate text-sm text-muted-foreground">{meta}</p>}
        {paper.status_error && <p className="mt-0.5 text-xs text-destructive">{paper.status_error}</p>}
      </div>
      {/* Ready is the normal state: announced, not shown. Only in-progress and failed papers get a visible badge. */}
      <Badge
        variant={paper.status === 'failed' ? 'destructive' : 'outline'}
        className={cn('status mt-1', paper.status === 'ready' && 'sr-only')}
      >
        {isIngesting(paper) && <LoaderCircle aria-hidden className="motion-safe:animate-spin" />}
        {paper.status}
      </Badge>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Delete"
        title="Delete"
        // Quiet until the row is in play: a red icon on every row would shout over the titles.
        className="relative z-10 text-muted-foreground group-focus-within:text-destructive group-hover:text-destructive hover:bg-destructive/10"
        onClick={() => onDelete(paper)}
      >
        <Trash2 aria-hidden />
      </Button>
    </li>
  )
}

export function LibraryPage() {
  const papers = usePapers()
  const upload = useUploadPapers()
  const remove = useDeletePaper()
  const fileInput = useRef<HTMLInputElement>(null)
  const hoverTimer = useRef<number | undefined>(undefined)
  const [previewId, setPreviewId] = useState<string | null>(null)

  useEffect(() => () => window.clearTimeout(hoverTimer.current), [])

  function preview(id: string, immediate: boolean) {
    window.clearTimeout(hoverTimer.current)
    if (immediate) setPreviewId(id)
    else hoverTimer.current = window.setTimeout(() => setPreviewId(id), HOVER_PREVIEW_DELAY_MS)
  }

  function onFiles(input: HTMLInputElement) {
    const files = [...(input.files ?? [])]
    input.value = ''
    if (files.length > 0) upload.mutate(files)
  }

  function onDelete(paper: Paper) {
    if (!window.confirm(`Delete "${paper.title}"? Its highlights go with it; notes are kept.`)) return
    remove.mutate(paper.id)
  }

  const error = upload.error ?? remove.error ?? papers.error
  const list = papers.data
  // Falls back to the first paper, so the panel is never empty and a deleted paper's preview goes away.
  const previewed = list?.find((paper) => paper.id === previewId) ?? list?.[0]

  return (
    <main className={cn('mx-auto flex max-w-6xl flex-col gap-4 px-4 py-6', fadeIn)}>
      <header className="flex items-center justify-between gap-2">
        <div>
          <h1 className="font-heading text-3xl font-semibold">PaperLab</h1>
          {list && list.length > 0 && (
            <p className="text-sm text-muted-foreground">
              {list.length} {list.length === 1 ? 'paper' : 'papers'}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" disabled={upload.isPending} onClick={() => fileInput.current?.click()}>
            <Upload aria-hidden />
            {upload.isPending ? 'Uploading…' : 'Upload PDFs'}
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf"
            multiple
            hidden
            onChange={(e) => onFiles(e.currentTarget)}
          />
          <ModeToggle />
        </div>
      </header>

      {error && (
        <Alert variant="destructive" className={cn('border-glass-border', glass)}>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}

      {list === undefined ? (
        papers.isError ? (
          <Button variant="outline" className="self-start" onClick={() => void papers.refetch()}>
            Retry
          </Button>
        ) : (
          <p className="text-muted-foreground">Loading…</p>
        )
      ) : list.length === 0 ? (
        <div className="grid place-items-center gap-2 rounded-xl border border-dashed border-glass-border px-6 py-16 text-center">
          <FileText aria-hidden className="size-8 text-muted-foreground" />
          <p className="text-muted-foreground">No papers yet. Upload a PDF to start.</p>
        </div>
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <Card className={cn('gap-0 py-0 ring-glass-border', glass)}>
            <ul className="divide-y divide-border">
              {list.map((paper) => (
                <PaperRow
                  key={paper.id}
                  paper={paper}
                  previewed={paper.id === previewed?.id}
                  onPreview={preview}
                  onDelete={onDelete}
                />
              ))}
            </ul>
          </Card>
          {/* Desktop only: the preview follows hover and focus, which a touch screen doesn't have. */}
          {previewed && (
            <div className="sticky top-6 hidden lg:block">
              <PaperPreview paper={previewed} />
            </div>
          )}
        </div>
      )}
    </main>
  )
}
