import { FileText, Plus } from 'lucide-react'
import { useState } from 'react'
import { useUploadPapers, useWorkspacePapers } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { FindPapersButton } from '@/features/discovery/FindPapersButton'
import { ErrorAlert, LoadError } from '@/features/library/ErrorAlert'
import { PaperList } from '@/features/library/PaperList'
import { UploadPdfsButton } from '@/features/library/UploadPdfsButton'
import { AddPapersDialog } from './AddPapersDialog'

/** The Papers tab: the library's rows for this workspace's papers, plus adding from the library or by upload. */
export function WorkspacePapers({ workspaceId }: { workspaceId: string }) {
  const papers = useWorkspacePapers(workspaceId)
  const upload = useUploadPapers(workspaceId)
  const [adding, setAdding] = useState(false)

  const list = papers.data
  return (
    <div className="flex flex-col gap-4 py-2">
      <div className="flex items-center gap-2">
        <Button onClick={() => setAdding(true)}>
          <Plus aria-hidden />
          Add papers
        </Button>
        <UploadPdfsButton variant="outline" isPending={upload.isPending} onUpload={(files) => upload.mutate(files)} />
        <FindPapersButton workspaceId={workspaceId} />
      </div>

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
          <p className="text-muted-foreground">No papers in this workspace yet. Add them from your library, or upload a PDF.</p>
        </div>
      ) : (
        <PaperList papers={list} workspaceId={workspaceId} />
      )}

      <AddPapersDialog workspaceId={workspaceId} open={adding} onOpenChange={setAdding} />
    </div>
  )
}
