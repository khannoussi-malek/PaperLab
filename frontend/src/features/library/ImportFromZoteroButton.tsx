import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileUp } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, type ImportProgress } from '@/api/client'
import { keys, refreshNotes } from '@/api/queries'
import { Hint } from '@/components/Hint'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { ImportResultView, plural } from './ImportResultView'

const POLL_MS = 2000
type Target = 'library' | 'workspace' | 'new'
const MB = 1024 * 1024
/** The size caps the API enforces: 200 MB for a zip, 20 MB for the text formats. */
const capFor = (file: File) => (/\.zip$/i.test(file.name) ? { mb: 200, what: 'a Zotero zip' } : { mb: 20, what: 'a .bib, .ris or .json file' })
const running = (p?: ImportProgress | null) => p?.state === 'queued' || p?.state === 'running'
/** Still being tracked: `unavailable` only means Redis couldn't be read for one poll; the job carries on. */
const tracking = (p?: ImportProgress | null) => running(p) || p?.state === 'unavailable'
/** The disclosure's general form, for when the preview failed and so can't say how many entries it covers. */
const GENERAL_DISCLOSURE =
  'Fetching contacts free-copy sources (Unpaywall, arXiv, …) for any entry without a PDF, the same way adding a paper by DOI does.'
/** The API's own code isn't meant for display. */
const inWords = (error: Error | null) =>
  error?.message === 'workspace_name_taken' ? new Error('A workspace with this name already exists.') : error

/** "Import from Zotero" and its dialog: a references file or Zotero zip into the library, or a workspace. */
export function ImportFromZoteroButton({ workspaceId, variant = 'outline' }: { workspaceId?: string; variant?: 'default' | 'outline' }) {
  return (
    <Dialog>
      <Hint hint="Bring in a Zotero export: .bib, .ris, CSL-JSON, or the zip with PDFs.">
        <DialogTrigger asChild>
          <Button variant={variant}>
            <FileUp aria-hidden />
            Import from Zotero
          </Button>
        </DialogTrigger>
      </Hint>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-xl')}>
        <DialogHeader>
          <DialogTitle>Import from Zotero</DialogTitle>
          <DialogDescription>Choose what Zotero exported, and where it should go.</DialogDescription>
        </DialogHeader>
        <ImportBody workspaceId={workspaceId} />
      </DialogContent>
    </Dialog>
  )
}

function ImportBody({ workspaceId }: { workspaceId?: string }) {
  const client = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [target, setTarget] = useState<Target>(workspaceId ? 'workspace' : 'library')
  const [name, setName] = useState('')
  const [fetchPdfs, setFetchPdfs] = useState(true)
  const [tooBig, setTooBig] = useState<string | null>(null)
  const started = useRef(false)

  const previewWorkspace = target === 'workspace' ? workspaceId : undefined
  const preview = useQuery({
    queryKey: ['citation-import-preview', file?.name, file?.size, file?.lastModified, previewWorkspace, fetchPdfs],
    // ponytail: every preview re-sends the whole file, so a 200 MB zip goes up 2-4 times (preview, switch or target
    // changes, then Import); upload once and preview by upload id if that ever hurts.
    queryFn: () => api.previewImport(file!, previewWorkspace, fetchPdfs),
    enabled: file !== null,
    placeholderData: keepPreviousData,
    retry: false,
    gcTime: 0,
  })

  const start = useMutation({
    // `into`: a retry goes into the workspace the first attempt already made, never under the new name again.
    mutationFn: (into?: string) => {
      started.current = true
      const where = into
        ? { workspaceId: into }
        : target === 'workspace'
          ? { workspaceId }
          : target === 'new'
            ? { newWorkspaceName: name.trim() }
            : {}
      return api.startImport(file!, where, fetchPdfs)
    },
  })
  // A closed dialog forgets the job but not the import: refresh the lists so its papers show up.
  useEffect(
    () => () => {
      if (!started.current) return
      void client.invalidateQueries({ queryKey: keys.papers })
      void client.invalidateQueries({ queryKey: keys.workspaces })
      void refreshNotes(client)
    },
    [client],
  )
  const jobId = tracking(start.data) ? start.data?.job_id : undefined
  const poll = useQuery({
    queryKey: ['citation-import', jobId],
    queryFn: () => api.importProgress(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => (tracking(q.state.data) || q.state.data === undefined ? POLL_MS : false),
  })
  const progress = poll.data ?? start.data

  useEffect(() => {
    if (progress?.state !== 'finished') return
    void client.invalidateQueries({ queryKey: keys.papers })
    void client.invalidateQueries({ queryKey: keys.workspaces })
    void refreshNotes(client)
  }, [progress?.state, client])

  if (progress && !start.isPending) {
    const into = progress.workspace_id ?? start.data?.workspace_id ?? undefined
    return <Outcome progress={progress} pollError={poll.error} onRetry={() => start.mutate(into)} />
  }

  const updating = preview.isFetching
  const ready = file !== null && !updating && (target !== 'new' || name.trim() !== '')
  const pv = preview.data
  // A failed preview can't say how many entries would be looked up, but Import is still allowed: say it generally.
  const generalDisclosure = fetchPdfs && !pv && preview.isError
  const error = tooBig ? new Error(tooBig) : inWords(start.error ?? preview.error)

  function pickFile(next: File | null) {
    const cap = next && capFor(next)
    if (next && cap && next.size > cap.mb * MB) {
      setFile(null)
      return setTooBig(`That file is over the ${cap.mb} MB limit for ${cap.what}.`)
    }
    setTooBig(null)
    setFile(next)
  }
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (ready) start.mutate()
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="zotero-file">References file</Label>
        <Input id="zotero-file" type="file" accept=".bib,.ris,.json,.zip" onChange={(e) => pickFile(e.currentTarget.files?.[0] ?? null)} />
        <p className="text-xs text-muted-foreground">
          A .bib, .ris or .json file (up to 20 MB), or a Zotero zip with PDFs (up to 200 MB).
        </p>
      </div>

      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1 text-sm font-medium">Where to put them</legend>
        <TargetOption value="library" current={target} onPick={setTarget} label="Library only" />
        {workspaceId && <TargetOption value="workspace" current={target} onPick={setTarget} label="This workspace" />}
        <TargetOption value="new" current={target} onPick={setTarget} label="A new workspace" />
        {target === 'new' && (
          <div className="flex flex-col gap-1.5 pl-6">
            <Label htmlFor="zotero-ws-name">Workspace name</Label>
            <Input id="zotero-ws-name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          </div>
        )}
      </fieldset>

      <div className="flex items-center gap-2">
        <Switch id="zotero-fetch" checked={fetchPdfs} onCheckedChange={setFetchPdfs} />
        <Label htmlFor="zotero-fetch">Fetch free PDFs for entries without one</Label>
      </div>

      <div aria-live="polite" className="flex flex-col gap-1 text-sm">
        {file && !pv && preview.isFetching && <p className="text-muted-foreground">Reading the file…</p>}
        {pv && (
          <p>
            {plural(pv.total, 'reference')}: {pv.already_in_library} already in your library
            {pv.with_bundled_pdf > 0 && `, ${pv.with_bundled_pdf} with a PDF in the zip`}.
          </p>
        )}
        {pv && pv.would_fetch > 0 && pv.disclosure && <p>{pv.disclosure}</p>}
        {generalDisclosure && <p>{GENERAL_DISCLOSURE}</p>}
        {pv && !fetchPdfs && pv.cannot_import_without_fetch > 0 && (
          <p>
            {plural(pv.cannot_import_without_fetch, 'reference')}{' '}
            {pv.cannot_import_without_fetch === 1 ? 'has' : 'have'} no PDF in the file and won't be imported unless
            fetching is on.
          </p>
        )}
        {updating && pv && <p className="text-muted-foreground">Updating…</p>}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}
      <Button type="submit" className="self-start" disabled={!ready || start.isPending}>
        {start.isPending ? 'Importing…' : 'Import'}
      </Button>
    </form>
  )
}

function TargetOption({ value, current, onPick, label }: { value: Target; current: Target; onPick: (t: Target) => void; label: string }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="radio" name="zotero-target" checked={current === value} onChange={() => onPick(value)} />
      {label}
    </label>
  )
}

const STATE_MESSAGES: Record<string, string> = {
  failed: 'The import stopped with an error.',
  restarted: 'PaperLab restarted before the import finished.',
  expired: 'That import is too old to look up.',
}

function Outcome({ progress, pollError, onRetry }: { progress: ImportProgress; pollError: Error | null; onRetry: () => void }) {
  if (progress.state === 'finished' && progress.result) return <ImportResultView result={progress.result} />
  if (progress.state === 'unavailable') {
    return (
      <p role="status" className="text-sm">
        Progress can't be read just now. The import carries on, and progress shows again once PaperLab reaches the
        background service.
      </p>
    )
  }
  if (running(progress)) {
    const c = progress.counts
    return (
      <p role="status" className="text-sm">
        {c && c.total > 0 ? `Importing… ${c.done} of ${c.total} references done.` : 'Waiting to start…'} You can close this;
        the import keeps running and its papers will appear in your library.
        {pollError && ` ${pollError.message}`}
      </p>
    )
  }
  return (
    <div className="flex flex-col items-start gap-3">
      <Alert variant="destructive">
        <AlertDescription>{progress.message ?? STATE_MESSAGES[progress.state] ?? 'The import did not finish.'}</AlertDescription>
      </Alert>
      <Button variant="outline" onClick={onRetry}>
        Try again
      </Button>
    </div>
  )
}
