import { FileText } from 'lucide-react'
import { usePapers, useUploadPapers } from '@/api/queries'
import { AppShell } from '@/components/AppShell'
import { delayedIn } from '@/components/motion'
import { Scene3D } from '@/features/scene3d/Scene3D'
import { cn } from '@/lib/utils'
import { FindPapersButton } from '../discovery/FindPapersButton'
import { ErrorAlert, LoadError } from './ErrorAlert'
import { PaperList } from './PaperList'
import { SearchNotice } from './SearchNotice'
import { UploadPdfsButton } from './UploadPdfsButton'

const loadLibraryScene = () => import('@/features/scene3d/directors/library')

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

export function LibraryPage() {
  const papers = usePapers()
  const upload = useUploadPapers()
  const list = papers.data

  return (
    <AppShell
      title="PaperLab"
      actions={
        <>
          <FindPapersButton />
          <UploadPdfsButton isPending={upload.isPending} onUpload={(files) => upload.mutate(files)} />
        </>
      }
      status={list && plural(list.length, 'paper')}
    >
      <div className="flex flex-col gap-4">
        <SearchNotice />

        {upload.error && <ErrorAlert message={upload.error.message} />}

        {list === undefined ? (
          papers.isError ? (
            <LoadError message={papers.error.message} onRetry={() => void papers.refetch()} />
          ) : (
            <p className={cn('text-muted-foreground', delayedIn)}>Loading…</p>
          )
        ) : list.length === 0 ? (
          <div className="grid place-items-center gap-2 rounded-xl border border-dashed border-glass-border px-6 py-16 text-center">
            <Scene3D
              load={loadLibraryScene}
              input={{ uploading: upload.isPending }}
              fallback={<FileText aria-hidden className="size-8 text-muted-foreground" />}
              className="h-48 w-64"
            />
            <p className="text-muted-foreground">No papers yet. Upload a PDF to start.</p>
          </div>
        ) : (
          <PaperList papers={list} />
        )}
      </div>
    </AppShell>
  )
}
