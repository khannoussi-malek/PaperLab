import { Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { useImportManuscript, useManuscripts } from '@/api/queries'
import type { Manuscript } from '@/api/client'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { LoadError } from '@/features/library/ErrorAlert'
import { EmptyState, TabSkeleton } from '@/features/workspaces/TabStates'
import { manuscriptHref } from '@/lib/route'
import { manuscriptFailure } from './errors'
import { NewManuscriptDialog } from './NewManuscriptDialog'

const STATE: Record<string, string> = {
  never: 'Not compiled yet',
  running: 'Compiling…',
  ok: 'Compiled',
  failed: 'Last compile failed',
}

export const skippedNotice = (skipped: string[]) =>
  skipped.length === 0
    ? 'Imported.'
    : `Imported. Skipped ${skipped.length} ${skipped.length === 1 ? 'file' : 'files'} PaperLab can't use yet: ${skipped.join(', ')}.`

function Row({ manuscript }: { manuscript: Manuscript }) {
  return (
    <li>
      <a
        href={manuscriptHref(manuscript.id)}
        className="flex items-center justify-between gap-3 rounded-lg border border-glass-border px-3 py-2 hover:bg-muted"
      >
        <span className="truncate font-medium">{manuscript.title}</span>
        <span className="shrink-0 text-sm text-muted-foreground">{STATE[manuscript.compile_status] ?? manuscript.compile_status}</span>
      </a>
    </li>
  )
}

/** A workspace's manuscripts (or, with null, the ones without a workspace), with New and Import actions. */
export function ManuscriptList({ workspaceId }: { workspaceId: string | null }) {
  const manuscripts = useManuscripts(workspaceId)
  const importZip = useImportManuscript()
  const [creating, setCreating] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const onFile = (input: HTMLInputElement) => {
    const file = input.files?.[0]
    input.value = ''
    if (!file) return
    setNotice(null)
    importZip.mutate({ file, workspaceId }, { onSuccess: (done) => setNotice(skippedNotice(done.skipped)) })
  }

  return (
    <div className="flex flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => setCreating(true)}>New manuscript</Button>
        <Button variant="outline" disabled={importZip.isPending} onClick={() => fileInput.current?.click()}>
          <Upload aria-hidden />
          {importZip.isPending ? 'Importing…' : 'Import Overleaf zip'}
        </Button>
        <input ref={fileInput} type="file" accept=".zip,application/zip" hidden onChange={(e) => onFile(e.currentTarget)} />
      </div>
      {notice && <p role="status" className="text-sm">{notice}</p>}
      {importZip.error && (
        <Alert variant="destructive"><AlertDescription>{manuscriptFailure(importZip.error)}</AlertDescription></Alert>
      )}
      {manuscripts.error && <LoadError message={manuscripts.error.message} onRetry={() => void manuscripts.refetch()} />}
      {manuscripts.isPending && <TabSkeleton label="Loading manuscripts" />}
      {manuscripts.data?.length === 0 && (
        <EmptyState title="No manuscripts yet">Start one from a template, or import a zip you downloaded from Overleaf.</EmptyState>
      )}
      {!!manuscripts.data?.length && (
        <ul className="flex flex-col gap-2">{manuscripts.data.map((m) => <Row key={m.id} manuscript={m} />)}</ul>
      )}
      <NewManuscriptDialog workspaceId={workspaceId} open={creating} onOpenChange={setCreating} />
    </div>
  )
}
