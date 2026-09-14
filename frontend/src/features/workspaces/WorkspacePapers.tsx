import { FileText, Plus, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { useUploadPapers, useWorkspacePapers } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { PaperList } from '@/features/library/PaperList'
import { cn } from '@/lib/utils'
import { AddPapersDialog } from './AddPapersDialog'

/** The Papers tab: the library's rows for this workspace's papers, plus adding from the library or by upload. */
export function WorkspacePapers({ workspaceId }: { workspaceId: string }) {
  const papers = useWorkspacePapers(workspaceId)
  const upload = useUploadPapers(workspaceId)
  const fileInput = useRef<HTMLInputElement>(null)
  const [adding, setAdding] = useState(false)

  function onFiles(input: HTMLInputElement) {
    const files = [...(input.files ?? [])]
    input.value = ''
    if (files.length > 0) upload.mutate(files)
  }

  const error = upload.error ?? papers.error
  const list = papers.data
  return (
    <div className="flex flex-col gap-4 py-2">
      <div className="flex items-center gap-2">
        <Button onClick={() => setAdding(true)}>
          <Plus aria-hidden />
          Add papers
        </Button>
        <Button variant="outline" disabled={upload.isPending} onClick={() => fileInput.current?.click()}>
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
      </div>

      {error && (
        <Alert variant="destructive" className={cn('border-glass-border', glass)}>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}

      {list === undefined ? (
        !papers.isError && <p className="text-muted-foreground">Loading…</p>
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
