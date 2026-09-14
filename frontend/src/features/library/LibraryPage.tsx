import { FileText, Upload } from 'lucide-react'
import { useRef } from 'react'
import { usePapers, useUploadPapers } from '@/api/queries'
import { glass } from '@/components/glass'
import { ModeToggle } from '@/components/mode-toggle'
import { fadeIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { WorkspaceSidebar } from '../workspaces/WorkspaceSidebar'
import { PaperList } from './PaperList'

export function LibraryPage() {
  const papers = usePapers()
  const upload = useUploadPapers()
  const fileInput = useRef<HTMLInputElement>(null)

  function onFiles(input: HTMLInputElement) {
    const files = [...(input.files ?? [])]
    input.value = ''
    if (files.length > 0) upload.mutate(files)
  }

  const error = upload.error ?? papers.error
  const list = papers.data

  return (
    <main className={cn('mx-auto flex max-w-7xl flex-col gap-4 px-4 py-6', fadeIn)}>
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

      <div className="grid items-start gap-4 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <WorkspaceSidebar activeId={null} />
        <div className="flex min-w-0 flex-col gap-4">
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
            <PaperList papers={list} />
          )}
        </div>
      </div>
    </main>
  )
}
