import { FilePlus, Lock, Pencil, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import type { ManuscriptFile } from '@/api/client'
import { useCreateManuscriptFile, useDeleteManuscriptFile, useRenameManuscriptFile, useUploadManuscriptFile } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { manuscriptHref } from '@/lib/route'
import { manuscriptErrorMessage, manuscriptFailure } from './errors'

// The server's rules (manuscript_paths.py), checked here first so a typo is caught before a round trip.
const TEXT = ['tex', 'bib', 'sty', 'cls', 'bst', 'txt', 'md', 'csv', 'dat', 'clo', 'def', 'cfg', 'bbx', 'cbx', 'tikz', 'pgf']
const BINARY = ['png', 'jpg', 'jpeg', 'pdf']
const SEGMENT = /^[A-Za-z0-9._-]+$/
const RESERVED = 'paperlab.bib'
const extension = (path: string) => {
  const name = path.split('/').pop() ?? ''
  return name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''
}
const isBinary = (path: string) => BINARY.includes(extension(path))

/** The error code the server would give `path`, or null when it is fine. `kinds` are the extensions allowed here. */
export function pathProblem(path: string, kinds: readonly string[]): string | null {
  const segments = path.split('/')
  if (segments.length > 4 || !segments.every((s) => SEGMENT.test(s) && s !== '.' && s !== '..')) return 'bad_path'
  if (segments[segments.length - 1].toLowerCase() === RESERVED) return 'reserved_path'
  if (!kinds.includes(extension(path)) && path.split('/').pop() !== 'latexmkrc') return 'unsupported_file_type'
  return null
}

type Props = {
  manuscriptId: string
  files: ManuscriptFile[]
  current: string
  main: string
  /** Saves the open file's pending text; false when it could not (a conflict), so nothing moves under it. */
  flushCurrent: () => Promise<boolean>
}
type Editing = { kind: 'new' } | { kind: 'rename'; path: string } | { kind: 'delete'; path: string } | null

function NameForm({ label, initial, busy, onSubmit, onCancel }: {
  label: string; initial: string; busy: boolean; onSubmit: (name: string) => void; onCancel: () => void
}) {
  const [name, setName] = useState(initial)
  return (
    <form className="flex flex-col gap-1 px-2 py-1" onSubmit={(e) => { e.preventDefault(); onSubmit(name.trim()) }}>
      <Input aria-label={label} value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="sections/intro.tex" />
      <span className="flex gap-1">
        <Button type="submit" size="xs" disabled={busy || !name.trim()}>Save</Button>
        <Button type="button" size="xs" variant="ghost" onClick={onCancel}>Cancel</Button>
      </span>
    </form>
  )
}

/**
 * The manuscript's files, each a link to `?file=` (figures are listed, not opened), with New file, Upload, Rename and
 * Delete; the main file can't be deleted. paperlab.bib is listed read-only: the compile writes it from the papers.
 */
export function FileList({ manuscriptId, files, current, main, flushCurrent }: Props) {
  const create = useCreateManuscriptFile()
  const upload = useUploadManuscriptFile()
  const rename = useRenameManuscriptFile()
  const remove = useDeleteManuscriptFile()
  const [editing, setEditing] = useState<Editing>(null)
  const [error, setError] = useState<string | null>(null)
  const uploadInput = useRef<HTMLInputElement>(null)
  const busy = create.isPending || upload.isPending || rename.isPending || remove.isPending
  const go = (path: string) => window.location.assign(manuscriptHref(manuscriptId, path))
  const done = () => { setEditing(null); setError(null) }
  const onError = (e: Error) => setError(manuscriptFailure(e))
  const refuse = (path: string, kinds: readonly string[]) => {
    const problem = pathProblem(path, kinds)
    if (problem) setError(manuscriptErrorMessage(problem, { path }))
    return problem !== null
  }

  const createFile = (path: string) => {
    if (refuse(path, TEXT)) return
    create.mutate({ id: manuscriptId, path }, { onSuccess: () => { done(); go(path) }, onError })
  }
  const renameFile = async (path: string, newPath: string) => {
    if (newPath === path) return done()
    if (refuse(newPath, [...TEXT, ...BINARY])) return
    if (path === current && !(await flushCurrent())) return // the editor shows why its save stopped
    rename.mutate({ id: manuscriptId, path, newPath }, { onSuccess: () => { done(); if (path === current) go(newPath) }, onError })
  }
  const deleteFile = (path: string) =>
    remove.mutate({ id: manuscriptId, path }, { onSuccess: () => { done(); if (path === current) go(main) }, onError })
  const onUpload = (input: HTMLInputElement) => {
    const file = input.files?.[0]
    input.value = ''
    if (!file || refuse(file.name, [...TEXT, ...BINARY])) return
    upload.mutate({ id: manuscriptId, path: file.name, file }, { onSuccess: done, onError })
  }

  return (
    <nav aria-label="Files">
      <div className="flex items-center justify-between px-2 pb-1">
        <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Files</h2>
        <span className="flex gap-1">
          <Button variant="ghost" size="icon-xs" aria-label="New file" title="New file" onClick={() => { setError(null); setEditing({ kind: 'new' }) }}>
            <FilePlus aria-hidden />
          </Button>
          <Button variant="ghost" size="icon-xs" aria-label="Upload a file" title="Upload a figure or a text file" disabled={upload.isPending} onClick={() => uploadInput.current?.click()}>
            <Upload aria-hidden />
          </Button>
          <input
            ref={uploadInput}
            type="file"
            hidden
            data-testid="upload-input"
            accept={[...TEXT, ...BINARY].map((e) => `.${e}`).join(',')}
            onChange={(e) => onUpload(e.currentTarget)}
          />
        </span>
      </div>
      {error && <Alert variant="destructive" className="mx-2 mb-1 w-auto"><AlertDescription>{error}</AlertDescription></Alert>}
      {editing?.kind === 'new' && <NameForm label="New file name" initial="" busy={busy} onSubmit={createFile} onCancel={done} />}
      <ul className="flex flex-col">
        {files.map((f) => (
          <li key={f.path}>
            <div className="group flex items-center gap-0.5">
              {isBinary(f.path) ? (
                <span title={`${f.path} (a figure; it can't be opened in the editor)`} className="block min-w-0 flex-1 truncate px-2 py-1 text-sm text-muted-foreground">
                  {f.path}
                </span>
              ) : (
                <a
                  href={manuscriptHref(manuscriptId, f.path)}
                  aria-current={f.path === current ? 'page' : undefined}
                  title={f.path === main ? `${f.path} (main file)` : f.path}
                  className={cn(
                    'block min-w-0 flex-1 truncate rounded-md px-2 py-1 text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50',
                    f.path === current && 'bg-muted font-medium',
                  )}
                >
                  {f.path}
                </a>
              )}
              <Button variant="ghost" size="icon-xs" aria-label={`Rename ${f.path}`} title="Rename" onClick={() => { setError(null); setEditing({ kind: 'rename', path: f.path }) }}>
                <Pencil aria-hidden />
              </Button>
              {f.path !== main && (
                <Button variant="ghost" size="icon-xs" aria-label={`Delete ${f.path}`} title="Delete" onClick={() => { setError(null); setEditing({ kind: 'delete', path: f.path }) }}>
                  <Trash2 aria-hidden />
                </Button>
              )}
            </div>
            {editing?.kind === 'rename' && editing.path === f.path && (
              <NameForm label={`New name for ${f.path}`} initial={f.path} busy={busy} onSubmit={(name) => void renameFile(f.path, name)} onCancel={done} />
            )}
            {editing?.kind === 'delete' && editing.path === f.path && (
              <div role="group" aria-label={`Delete ${f.path}?`} className="flex flex-col gap-1 px-2 py-1 text-sm">
                <span>Delete {f.path}? This can't be undone.</span>
                <span className="flex gap-1">
                  <Button size="xs" variant="destructive" disabled={busy} onClick={() => deleteFile(f.path)}>Delete</Button>
                  <Button size="xs" variant="ghost" onClick={done}>Cancel</Button>
                </span>
              </div>
            )}
          </li>
        ))}
        <li className="flex items-center gap-1 px-2 py-1 text-sm text-muted-foreground" title="Generated from the workspace's papers each time you compile">
          <Lock aria-hidden className="size-3" />
          <span>paperlab.bib</span>
          <span className="sr-only">(read-only)</span>
        </li>
      </ul>
      <p className="px-2 text-xs text-muted-foreground">paperlab.bib is generated from the workspace's papers when you compile. You can't edit it.</p>
    </nav>
  )
}
