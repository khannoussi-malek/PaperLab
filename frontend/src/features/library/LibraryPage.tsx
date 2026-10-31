import { FileText } from 'lucide-react'
import { useState } from 'react'
import { usePapers, useUploadPapers } from '@/api/queries'
import { AppShell } from '@/components/AppShell'
import { Button } from '@/components/ui/button'
import { delayedIn } from '@/components/motion'
import { Scene3D } from '@/features/scene3d/Scene3D'
import { cn } from '@/lib/utils'
import { FindPapersButton } from '../discovery/FindPapersButton'
import { ExportSelectedMenu } from '../workspaces/ExportSelectedMenu'
import { ManuscriptList } from '../manuscripts/ManuscriptList'
import { useManuscripts } from '@/api/queries'
import { ErrorAlert, LoadError } from './ErrorAlert'
import { PaperList } from './PaperList'
import { FoundPdfsNotice } from './FoundPdfsNotice'
import { ViewSwitch, usePaperView } from './ViewSwitch'
import { SearchNotice } from './SearchNotice'
import { ImportFromZoteroButton } from './ImportFromZoteroButton'
import { UploadPdfsButton } from './UploadPdfsButton'

const loadLibraryScene = () => import('@/features/scene3d/directors/library')

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

export function LibraryPage() {
  const orphans = useManuscripts(null)
  const papers = usePapers()
  const upload = useUploadPapers()
  const list = papers.data
  const [view, setView, exitTriage] = usePaperView('paperlab-library-view', 'library')
  const [visible, setVisible] = useState<string[] | null>(null)
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set())
  // A pick hidden by the list's own search is kept, but only the rows on screen are counted and exported.
  const selectedIds = (list ?? []).filter((p) => picked.has(p.id) && (visible?.includes(p.id) ?? true)).map((p) => p.id)
  const toggle = (id: string) => setPicked((prev) => new Set(prev.has(id) ? [...prev].filter((x) => x !== id) : [...prev, id]))

  return (
    <AppShell
      title="PaperLab"
      actions={
        <>
          <FindPapersButton />
          <ImportFromZoteroButton />
          <UploadPdfsButton isPending={upload.isPending} onUpload={(files) => upload.mutate(files)} />
        </>
      }
      status={list && plural(list.length, 'paper')}
    >
      <div className="flex flex-col gap-4">
        <SearchNotice />
        <FoundPdfsNotice />

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
            <p className="text-muted-foreground">No papers yet. Upload a PDF, or add one by DOI.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <ViewSwitch view={view} onChange={setView} />
            {view === 'list' && selectedIds.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span role="status" className="text-sm">{selectedIds.length} selected</span>
                <ExportSelectedMenu paperIds={selectedIds} />
                <Button variant="ghost" size="sm" onClick={() => setPicked(new Set())}>Clear</Button>
              </div>
            )}
            <PaperList papers={list} selection={view === 'list' ? { selected: new Set(selectedIds), onToggle: toggle } : undefined} onVisibleChange={setVisible} view={view} triageScope="library" sourceLabel="your library" onTriageExit={exitTriage} onShowKept={() => setView('list')} />
          </div>
        )}

        {!!orphans.data?.length && (
          <section aria-labelledby="orphan-manuscripts" className="flex flex-col gap-1">
            <h2 id="orphan-manuscripts" className="text-base font-medium">Manuscripts without a workspace</h2>
            <ManuscriptList workspaceId={null} />
          </section>
        )}
      </div>
    </AppShell>
  )
}
