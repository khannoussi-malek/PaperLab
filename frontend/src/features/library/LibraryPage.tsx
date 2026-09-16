import { ChartColumn, FileText, Settings } from 'lucide-react'
import { usePapers, useUploadPapers } from '@/api/queries'
import { ModeToggle } from '@/components/mode-toggle'
import { fadeIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { chartsHref, settingsHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { FindPapersButton } from '../discovery/FindPapersButton'
import { WorkspaceSidebar } from '../workspaces/WorkspaceSidebar'
import { ErrorAlert, LoadError } from './ErrorAlert'
import { PaperList } from './PaperList'
import { UploadPdfsButton } from './UploadPdfsButton'

export function LibraryPage() {
  const papers = usePapers()
  const upload = useUploadPapers()
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
          <Button variant="outline" asChild>
            <a href={chartsHref}>
              <ChartColumn aria-hidden />
              Charts
            </a>
          </Button>
          <FindPapersButton />
          <UploadPdfsButton isPending={upload.isPending} onUpload={(files) => upload.mutate(files)} />
          <Button variant="outline" size="icon" asChild>
            <a href={settingsHref} aria-label="Settings">
              <Settings aria-hidden />
            </a>
          </Button>
          <ModeToggle />
        </div>
      </header>

      <div className="grid items-start gap-4 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <WorkspaceSidebar activeId={null} />
        <div className="flex min-w-0 flex-col gap-4">
          {upload.error && <ErrorAlert message={upload.error.message} />}

          {list === undefined ? (
            papers.isError ? (
              <LoadError message={papers.error.message} onRetry={() => void papers.refetch()} />
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
