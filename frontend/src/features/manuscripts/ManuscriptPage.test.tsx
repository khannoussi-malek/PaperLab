// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, type ManuscriptDetail } from '@/api/client'
import { keptTexts } from './keptTexts'
import { ManuscriptPage } from './ManuscriptPage'

const pdf = vi.hoisted(() => vi.fn((_url: string | null) => ({ doc: null, error: null })))
// jsdom can't lay CodeMirror out, so here the editor is a textarea with the same props (LatexEditor.test.tsx runs the real one).
type EditorProps = { value: string; onChange: (v: string) => void; onCursor?: (l: number) => void; onSectionStep?: (s: -1 | 1) => void; onShowInPdf?: (l: number) => void; onCiteKey?: (k: string) => void; registerInsert?: (f: ((t: string) => void) | null) => void; jumpTo?: { line: number; n: number } | null }
const editor = vi.hoisted(() => ({ current: null as null | EditorProps }))
vi.mock('./LatexEditor', async () => {
  const { useEffect, useRef } = await import('react')
  return {
    LatexEditor: (props: EditorProps) => {
      editor.current = props
      const now = useRef(props)
      now.current = props
      // Like the real one: an insert is a normal edit at the end here (the cursor logic is tested in LatexEditor.test.tsx).
      useEffect(() => { props.registerInsert?.((t) => now.current.onChange(now.current.value + t)); return () => props.registerInsert?.(null) }, [])
      return <textarea aria-label="LaTeX source" value={props.value} onChange={(e) => props.onChange(e.target.value)} />
    },
  }
})
vi.mock('@/components/AppShell', () => ({
  AppShell: ({ title, actions, status, children }: { title: string; actions?: React.ReactNode; status?: React.ReactNode; children: React.ReactNode }) => (
    <div><h1>{title}</h1>{actions}<main>{children}</main>{status}</div>
  ),
}))
vi.mock('../reader/usePdfDocument', () => ({ usePdfDocument: pdf }))
vi.mock('../reader/PdfPage', () => ({ PdfPage: () => null }))

const T2 = '2026-10-02T00:00:00Z'
const T3 = '2026-10-03T00:00:00Z'
const T4 = '2026-10-04T00:00:00Z'
const detail = (over: Partial<ManuscriptDetail> = {}): ManuscriptDetail => ({
  id: 'm1', workspace_id: 'w1', title: 'Thesis', main_file: 'main.tex', checklist: {}, compile_status: 'idle',
  compile_requested: false, compiled_at: null, compile_log: null, compile_friendly: null, compile_errors: [],
  created_at: '2026-10-01T00:00:00Z', updated_at: T2,
  files: [{ path: 'main.tex', size: 5, updated_at: T2 }, { path: 'b.tex', size: 3, updated_at: T2 }], ...over,
})
const conflict = () => new ApiError('file_changed', 409, { detail: 'file_changed', updated_at: T3 })
const saved = (at = T4) => ({ path: 'main.tex', size: 11, updated_at: at })

let server: Record<string, { text: string; at: string }>

function renderPage(file: string | null = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (f: string | null) => <QueryClientProvider client={client}><ManuscriptPage manuscriptId="m1" file={f} /></QueryClientProvider>
  const view = render(ui(file))
  return { ...view, open: (f: string | null) => view.rerender(ui(f)) }
}

async function type(text: string, expectedBefore = 'hello') {
  const box = await screen.findByLabelText('LaTeX source')
  await waitFor(() => expect(box).toHaveValue(expectedBefore))
  fireEvent.change(box, { target: { value: text } })
  return box
}
const ctrlS = (box: HTMLElement) => fireEvent.keyDown(box, { key: 's', ctrlKey: true })
// Every kept text for the manuscript, sorted.
const allKept = () => keptTexts.forManuscript('m1').map((k) => k.text).sort()
const keep = (path: string, text: string, base = T2) => keptTexts.put('m1', { path, text, reason: 'error', base, seq: keptTexts.nextSeq() })

beforeEach(() => {
  keptTexts.clear()
  server = { 'main.tex': { text: 'hello', at: T2 }, 'b.tex': { text: 'bee', at: T2 } }
  pdf.mockClear()
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail())
  vi.spyOn(api, 'getManuscriptFile').mockImplementation(async (_id, path) => ({ path, text: server[path].text, updated_at: server[path].at }))
  vi.spyOn(api, 'listManuscriptSnapshots').mockResolvedValue([{ id: 's1', reason: 'compile', created_at: T2 }])
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('shows the conflict banner with both choices', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(conflict())
  renderPage()
  ctrlS(await type('hello world'))
  expect(await screen.findByRole('alert')).toHaveTextContent('changed somewhere else')
  expect(screen.getByRole('button', { name: 'Keep my version' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Load theirs' })).toBeInTheDocument()
  expect(screen.getByText('Changed in another tab')).toBeInTheDocument()
  expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello world') // nothing is discarded without a click
})

test('Keep my version saves my text over the newest server version', async () => {
  const save = vi.spyOn(api, 'saveManuscriptFile').mockRejectedValueOnce(conflict()).mockResolvedValue(saved())
  renderPage()
  ctrlS(await type('hello world'))
  fireEvent.click(await screen.findByRole('button', { name: 'Keep my version' }))
  await waitFor(() => expect(save).toHaveBeenCalledTimes(2))
  expect(save).toHaveBeenLastCalledWith('m1', 'main.tex', 'hello world', T3)
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Keep my version' })).toBeNull())
})

test('Load theirs shows the server text and saves nothing', async () => {
  const save = vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(conflict())
  renderPage()
  ctrlS(await type('hello world'))
  server['main.tex'] = { text: 'theirs', at: T3 }
  fireEvent.click(await screen.findByRole('button', { name: 'Load theirs' }))
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('theirs'))
  expect(save).toHaveBeenCalledOnce()
  expect(screen.getByText('Saved')).toBeInTheDocument()
})

test('Ctrl+S saves then compiles', async () => {
  const order: string[] = []
  const save = vi.spyOn(api, 'saveManuscriptFile').mockImplementation(async () => { order.push('save'); return saved() })
  vi.spyOn(api, 'compileManuscript').mockImplementation(async () => { order.push('compile'); return { state: 'queued' } })
  renderPage()
  ctrlS(await type('hello world'))
  await waitFor(() => expect(order).toEqual(['save', 'compile']))
  expect(save).toHaveBeenCalledWith('m1', 'main.tex', 'hello world', T2)
})

test('Ctrl+S does not compile while a compile is running', async () => {
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail({ compile_status: 'running' }))
  const save = vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  const compile = vi.spyOn(api, 'compileManuscript').mockResolvedValue({ state: 'queued' })
  renderPage()
  ctrlS(await type('hello world'))
  await waitFor(() => expect(save).toHaveBeenCalled())
  expect(compile).not.toHaveBeenCalled()
})

test('shows the friendly message the worker stored, naming the missing package', async () => {
  vi.spyOn(api, 'getManuscript').mockResolvedValue(
    detail({
      compile_status: 'failed', compile_friendly: 'package_missing', compile_log: '', compiled_at: T3,
      compile_errors: [{ file: 'main.tex', line: null, message: 'fontawesome5', kind: 'package_missing' }],
    }),
  )
  renderPage()
  expect(await screen.findByRole('alert')).toHaveTextContent("This project uses a LaTeX package PaperLab doesn't include yet: fontawesome5.")
})

test('an interrupted compile says so and Compile is offered again', async () => {
  vi.spyOn(api, 'getManuscript').mockResolvedValue(
    detail({ compile_status: 'failed', compile_friendly: 'compile_interrupted', compile_requested: false, compiled_at: null }),
  )
  renderPage()
  expect(await screen.findByRole('alert')).toHaveTextContent('The last compile was interrupted. Compile again.')
  expect(await screen.findByRole('button', { name: /^Compile/ })).toBeEnabled()
})

test('History names each kind of snapshot', async () => {
  vi.spyOn(api, 'listManuscriptSnapshots').mockResolvedValue([
    { id: 's1', reason: 'compile', created_at: T2 }, { id: 's2', reason: 'autosave', created_at: T2 },
    { id: 's3', reason: 'before_restore', created_at: T2 },
  ])
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'History' }))
  for (const label of ['Compiled', 'Autosaved', 'Before a restore']) expect(await screen.findByText(label)).toBeInTheDocument()
  expect(screen.queryByText('autosave')).toBeNull()
})

test('a failed compile keeps the last PDF on screen', async () => {
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail({ compile_status: 'failed', compiled_at: T3 }))
  renderPage()
  await screen.findByRole('alert')
  expect(pdf).toHaveBeenCalledWith(expect.stringContaining('/api/manuscripts/m1/pdf?v='))
})

test('leaving a file whose save fails keeps the text and offers to reopen it', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new Error('network down'))
  const view = renderPage()
  await type('hello world')
  view.open('b.tex')
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('main.tex')
  expect(screen.getByRole('link', { name: 'Open it' })).toHaveAttribute('href', '#/manuscripts/m1?file=main.tex')
  view.open('main.tex')
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello world'))
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Open it' })).toBeNull()
})

test('leaving a file that conflicts keeps the text and reopens it as a conflict', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(conflict())
  const view = renderPage()
  await type('hello world')
  view.open('b.tex')
  expect(await screen.findByRole('link', { name: 'Open it' })).toBeInTheDocument()
  view.open('main.tex')
  expect(await screen.findByRole('button', { name: 'Keep my version' })).toBeInTheDocument()
  expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello world')
})

test('asks the browser to confirm leaving while a save is pending', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  renderPage()
  await type('hello world')
  const event = new Event('beforeunload', { cancelable: true })
  window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
})

async function openRestore() {
  fireEvent.click(await screen.findByRole('button', { name: 'History' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Restore…' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Restore' }))
}

test('Restore saves what is pending first, then restores', async () => {
  const order: string[] = []
  vi.spyOn(api, 'saveManuscriptFile').mockImplementation(async () => { order.push('save'); return saved() })
  vi.spyOn(api, 'restoreManuscriptSnapshot').mockImplementation(async () => { order.push('restore') })
  renderPage()
  await type('hello world')
  await openRestore()
  await waitFor(() => expect(order).toEqual(['save', 'restore']))
})

test('Restore stops at a conflict and shows it', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(conflict())
  const restore = vi.spyOn(api, 'restoreManuscriptSnapshot').mockResolvedValue(undefined)
  renderPage()
  await type('hello world')
  await openRestore()
  expect(await screen.findByRole('button', { name: 'Keep my version' })).toBeInTheDocument()
  expect(restore).not.toHaveBeenCalled()
})

test('after a restore the open file shows the restored text', async () => {
  vi.spyOn(api, 'restoreManuscriptSnapshot').mockImplementation(async () => { server['main.tex'] = { text: 'restored', at: T3 } })
  renderPage()
  await screen.findByLabelText('LaTeX source')
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello'))
  await openRestore()
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('restored'))
})

test('kept text edited against an older version reopens as a conflict, not a silent overwrite', async () => {
  keep('main.tex', 'mine')
  server['main.tex'] = { text: 'newer', at: T3 }
  const save = vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  renderPage()
  expect(await screen.findByRole('button', { name: 'Keep my version' })).toBeInTheDocument()
  expect(screen.getByLabelText('LaTeX source')).toHaveValue('mine')
  expect(save).not.toHaveBeenCalled()
})

test('kept text survives leaving the page and coming back', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new Error('network down'))
  const first = renderPage()
  await type('hello world')
  first.unmount()
  await waitFor(() => expect(keptTexts.forManuscript('m1')).toMatchObject([{ text: 'hello world', base: T2 }]))
  const second = renderPage('b.tex')
  expect(await screen.findByRole('link', { name: 'Open it' })).toHaveAttribute('href', '#/manuscripts/m1?file=main.tex')
  second.open('main.tex')
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello world'))
})

test('kept text is dropped once it is saved', async () => {
  keep('main.tex', 'mine')
  vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  renderPage()
  await screen.findByText('Unsaved changes')
  await waitFor(() => expect(allKept()).toEqual([]), { timeout: 3000 })
})

test('a 4xx save error shows its message and does not say it will retry', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new ApiError('file_too_large', 413, { detail: 'file_too_large', limit: 5242880 }))
  renderPage()
  ctrlS(await type('hello world'))
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('bigger than 5 MB')
  expect(alert).not.toHaveTextContent('Trying again')
})

test('a network error says it will try again', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new TypeError('Failed to fetch'))
  renderPage()
  ctrlS(await type('hello world'))
  expect(await screen.findByRole('alert')).toHaveTextContent('Trying again shortly')
})

test('Load theirs keeps my text and the conflict when the refetch fails', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(conflict())
  renderPage()
  ctrlS(await type('hello world'))
  const load = await screen.findByRole('button', { name: 'Load theirs' })
  ;(api.getManuscriptFile as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('offline'))
  fireEvent.click(load)
  expect(await screen.findByText('offline')).toBeInTheDocument()
  expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello world')
  expect(screen.getByRole('button', { name: 'Keep my version' })).toBeInTheDocument()
})

test('a late failing flush from an earlier pane is not lost when the file is reopened and saved', async () => {
  let failFirst: (error: Error) => void = () => {}
  const save = vi.spyOn(api, 'saveManuscriptFile')
    .mockImplementationOnce(() => new Promise((_, reject) => { failFirst = reject }))
    .mockResolvedValue(saved())
  const view = renderPage()
  await type('hello world')
  view.open('b.tex') // the first pane closes with its save in flight
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  view.open('main.tex') // a second pane opens from the cache, before the first save settles
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello'))
  failFirst(new Error('network down'))
  await waitFor(() => expect(allKept()).toEqual(['hello world']))
  expect(await screen.findByRole('button', { name: 'Use it' })).toBeInTheDocument()
  ctrlS(await type('another edit'))
  await waitFor(() => expect(screen.getByText('Saved')).toBeInTheDocument())
  expect(allKept()).toEqual(['hello world']) // not this pane's to remove
  expect(screen.getByRole('button', { name: 'Use it' })).toBeInTheDocument()
})

test('Use it puts the kept text into the editor, unsaved', async () => {
  renderPage()
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello'))
  keep('main.tex', 'kept text')
  fireEvent.click(await screen.findByRole('button', { name: 'Use it' }))
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('kept text'))
  expect(screen.getByText('Unsaved changes')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Use it' })).toBeNull()
})

test('Use it on text from an older version is a conflict to resolve', async () => {
  renderPage()
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello'))
  keep('main.tex', 'kept text', '2026-09-01T00:00:00Z')
  fireEvent.click(await screen.findByRole('button', { name: 'Use it' }))
  expect(await screen.findByRole('button', { name: 'Keep my version' })).toBeInTheDocument()
})

test('Discard drops a kept text', async () => {
  keep('b.tex', 'old')
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Discard' }))
  expect(allKept()).toEqual([])
  expect(screen.queryByRole('link', { name: 'Open it' })).toBeNull()
})

test('a1: an earlier pane\'s late failure and the reopened pane\'s failure both survive', async () => {
  let failFirst: (error: Error) => void = () => {}
  const save = vi.spyOn(api, 'saveManuscriptFile')
    .mockImplementationOnce(() => new Promise((_, reject) => { failFirst = reject }))
    .mockRejectedValue(new Error('network down'))
  const view = renderPage()
  await type('first copy')
  view.open('b.tex') // the first pane's save hangs
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  view.open('main.tex')
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello'))
  failFirst(new Error('network down')) // the first copy is kept while the second pane is open
  expect(await screen.findByRole('button', { name: 'Use it' })).toBeInTheDocument()
  await type('second copy')
  view.open('b.tex') // offline: the second pane's save fails too
  await waitFor(() => expect(screen.getAllByRole('link', { name: 'Open it' })).toHaveLength(2))
  expect(allKept()).toEqual(['first copy', 'second copy'])
  view.open('main.tex') // two copies: neither is taken over unasked
  await waitFor(() => expect(screen.getAllByRole('button', { name: 'Use it' })).toHaveLength(2))
  expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello')
})

test('a2: the reopened pane failing first does not shut out the earlier pane\'s late failure', async () => {
  let failFirst: (error: Error) => void = () => {}
  const save = vi.spyOn(api, 'saveManuscriptFile')
    .mockImplementationOnce(() => new Promise((_, reject) => { failFirst = reject }))
    .mockRejectedValue(new Error('network down'))
  const view = renderPage()
  await type('first copy')
  view.open('b.tex')
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  view.open('main.tex') // nothing to take over yet
  await type('second copy')
  view.open('b.tex')
  await waitFor(() => expect(allKept()).toEqual(['second copy']))
  failFirst(new Error('network down'))
  await waitFor(() => expect(screen.getAllByRole('link', { name: 'Open it' })).toHaveLength(2))
  expect(allKept()).toEqual(['first copy', 'second copy'])
})

test('Discard drops only the copy it was shown for', async () => {
  keep('main.tex', 'one')
  keep('main.tex', 'two')
  renderPage('b.tex')
  await waitFor(() => expect(screen.getAllByRole('button', { name: 'Discard' })).toHaveLength(2))
  fireEvent.click(screen.getAllByRole('button', { name: 'Discard' })[0])
  expect(allKept()).toEqual(['two'])
  expect(screen.getAllByRole('link', { name: 'Open it' })).toHaveLength(1)
})

test('using one of two copies and saving it drops only that copy', async () => {
  keep('main.tex', 'one')
  keep('main.tex', 'two')
  const save = vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  renderPage()
  await waitFor(() => expect(screen.getAllByRole('button', { name: 'Use it' })).toHaveLength(2))
  expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello')
  fireEvent.click(screen.getAllByRole('button', { name: 'Use it' })[0])
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('one'))
  await waitFor(() => expect(save).toHaveBeenCalledWith('m1', 'main.tex', 'one', T2))
  await waitFor(() => expect(allKept()).toEqual(['two']))
  expect(screen.getAllByRole('button', { name: 'Use it' })).toHaveLength(1)
})

test('a pane that took over a copy and fails again replaces that copy, not adds to it', async () => {
  keep('main.tex', 'kept')
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new Error('network down'))
  const view = renderPage()
  await type('kept, edited', 'kept')
  view.open('b.tex')
  await waitFor(() => expect(allKept()).toEqual(['kept, edited']))
})

test('the header moves the manuscript and deletes it after asking in the app', async () => {
  vi.spyOn(api, 'listWorkspaces').mockResolvedValue([{ id: 'w1', name: 'Sleep' }, { id: 'w2', name: 'Memory' }] as never)
  const update = vi.spyOn(api, 'updateManuscript').mockResolvedValue(detail({ workspace_id: 'w2' }))
  const remove = vi.spyOn(api, 'deleteManuscript').mockResolvedValue(undefined)
  renderPage()
  fireEvent.click(await screen.findByRole('button', { name: 'Move' }))
  await screen.findByRole('option', { name: 'Memory' })
  fireEvent.change(screen.getByLabelText('Workspace'), { target: { value: 'w2' } })
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Move' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('m1', { workspace_id: 'w2' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Delete manuscript' }))
  await waitFor(() => expect(remove).toHaveBeenCalledWith('m1'))
  await waitFor(() => expect(window.location.hash).toBe('#/workspaces/w1?tab=write'))
})

test('the left column lists sections from main.tex, with the other files under All files', async () => {
  server = {
    'main.tex': { text: '\\input{sections/intro}', at: T2 },
    'sections/intro.tex': { text: '\\section{Introduction}\nhi', at: T2 },
  }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail({
    files: [{ path: 'main.tex', size: 5, updated_at: T2 }, { path: 'sections/intro.tex', size: 3, updated_at: T2 }],
  }))
  renderPage()
  expect(await screen.findByRole('button', { name: /^1\s*Introduction/ })).toBeInTheDocument()
  expect(screen.getByText('All files')).toBeInTheDocument()
  expect(screen.queryByRole('navigation', { name: 'Outline' })).toBeNull()
})

test('the breadcrumb follows the cursor, and Mod+Alt+Down opens the next section', async () => {
  server = {
    'main.tex': { text: '\\input{sections/a}\n\\input{sections/b}', at: T2 },
    'sections/a.tex': { text: '\\section{Method}\nx\n\\subsection{Data}\ny', at: T2 },
    'sections/b.tex': { text: '\\section{Results}\nz', at: T2 },
  }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail({
    files: ['main.tex', 'sections/a.tex', 'sections/b.tex'].map((p) => ({ path: p, size: 5, updated_at: T2 })),
  }))
  window.location.hash = ''
  renderPage('sections/a.tex')
  await screen.findByLabelText('LaTeX source')
  await waitFor(() => expect(editor.current?.onCursor).toBeDefined())
  act(() => editor.current!.onCursor!(4))
  const crumbs = await screen.findByRole('navigation', { name: 'Where you are' })
  expect(crumbs).toHaveTextContent('Method›Data')
  act(() => editor.current!.onSectionStep!(1))
  await waitFor(() => expect(window.location.hash).toContain('sections%2Fb.tex'))
})

// --- PDF <-> source ---
const GOOD = { compile_status: 'ok' as const, compiled_at: T3 }
const pages = () => screen.getByLabelText('PDF pages')
const withPdf = () => pdf.mockReturnValue({ doc: { numPages: 3 } as never, error: null })

test('showing a line in the PDF scrolls to the page the lookup returns', async () => {
  withPdf()
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  const forward = vi.spyOn(api, 'syncForward').mockResolvedValue({ page: 2, x: 72, y: 300 })
  renderPage()
  await screen.findByLabelText('LaTeX source')
  await waitFor(() => expect(forward).toHaveBeenCalledWith('m1', 'main.tex', 1)) // once per new good compile
  forward.mockClear()
  act(() => editor.current!.onShowInPdf!(7))
  await waitFor(() => expect(forward).toHaveBeenCalledWith('m1', 'main.tex', 7))
  const page2 = pages().querySelector('[data-page="2"]')
  expect(page2).not.toBeNull()
})

test('opening a section looks its line up', async () => {
  withPdf()
  server['sections/x.tex'] = { text: '\\section{X}\nhi', at: T2 }
  server['main.tex'] = { text: '\\input{sections/x}', at: T2 }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail({ files: [...detail().files, { path: 'sections/x.tex', size: 3, updated_at: T2 }] }))
  const forward = vi.spyOn(api, 'syncForward').mockResolvedValue({ page: 3, x: 0, y: 10 })
  renderPage('sections/x.tex')
  fireEvent.click(await screen.findByRole('button', { name: /^1\s*X/ }))
  await waitFor(() => expect(forward).toHaveBeenCalledWith('m1', 'sections/x.tex', 1))
})

test('ctrl-click on a page opens the source the lookup names', async () => {
  withPdf()
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail())
  const inverse = vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'b.tex', line: 12 })
  renderPage()
  await screen.findByLabelText('LaTeX source')
  fireEvent.click(pages().querySelector('[data-page="2"]')!, { ctrlKey: true, clientX: 0, clientY: 0 })
  await waitFor(() => expect(inverse).toHaveBeenCalledWith('m1', 2, expect.any(Number), expect.any(Number)))
  await waitFor(() => expect(window.location.hash).toBe('#/manuscripts/m1?file=b.tex&line=12'))
  window.location.hash = ''
})

test('no_sync is silent', async () => {
  withPdf()
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  const forward = vi.spyOn(api, 'syncForward').mockRejectedValue(new ApiError('no_sync', 404, { detail: 'no_sync' }))
  vi.spyOn(api, 'syncInverse').mockRejectedValue(new ApiError('no_sync', 404, { detail: 'no_sync' }))
  renderPage()
  await waitFor(() => expect(forward).toHaveBeenCalled())
  fireEvent.click(pages().querySelector('[data-page="1"]')!, { metaKey: true })
  await new Promise((r) => setTimeout(r, 0))
  expect(screen.queryByRole('alert')).toBeNull()
})

const deferred = <T,>() => { let resolve!: (v: T) => void; const promise = new Promise<T>((r) => { resolve = r }); return { promise, resolve } }

test('only the newest forward lookup moves the PDF', async () => {
  withPdf()
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail())
  const first = deferred<{ page: number; x: number; y: number }>()
  const second = deferred<{ page: number; x: number; y: number }>()
  vi.spyOn(api, 'syncForward').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
  renderPage()
  await screen.findByLabelText('LaTeX source')
  act(() => editor.current!.onShowInPdf!(3))
  act(() => editor.current!.onShowInPdf!(5))
  await act(async () => { second.resolve({ page: 2, x: 0, y: 999 }) })
  const landed = pages().scrollTop
  expect(landed).toBeGreaterThan(300)
  await act(async () => { first.resolve({ page: 1, x: 0, y: 100 }) }) // older answer arrives late
  expect(pages().scrollTop).toBe(landed)
})

test('an inverse lookup that answers after another file opened is dropped', async () => {
  withPdf()
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail())
  const late = deferred<{ file: string; line: number }>()
  vi.spyOn(api, 'syncInverse').mockReturnValue(late.promise)
  const view = renderPage()
  await screen.findByLabelText('LaTeX source')
  fireEvent.click(pages().querySelector('[data-page="1"]')!, { ctrlKey: true })
  view.open('b.tex')
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('bee'))
  await act(async () => { late.resolve({ file: 'b.tex', line: 99 }) })
  expect(editor.current!.jumpTo?.line).not.toBe(99)
  expect(window.location.hash).toBe('')
})

test('?line= on the same file jumps again', async () => {
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail())
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (l: number) => <QueryClientProvider client={client}><ManuscriptPage manuscriptId="m1" file="b.tex" line={l} /></QueryClientProvider>
  const view = render(ui(3))
  await waitFor(() => expect(editor.current?.jumpTo?.line).toBe(3))
  view.rerender(ui(8))
  await waitFor(() => expect(editor.current?.jumpTo?.line).toBe(8))
})

// ---- edit from the PDF ----
const dbl = (word: string, page = 1) => {
  vi.spyOn(window, 'getSelection').mockReturnValue({ toString: () => word, rangeCount: 0 } as unknown as Selection)
  fireEvent.doubleClick(pages().querySelector(`[data-page="${page}"]`)!, { clientX: 5, clientY: 5 })
}
const editBox = () => screen.findByRole('textbox', { name: 'Edit this text' })

test('double-click edits the sentence through the open editor, then compiles', async () => {
  withPdf()
  server['main.tex'] = { text: 'Intro line.\nWe study cats. Dogs bark.', at: T2 }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'syncForward').mockRejectedValue(new Error('x'))
  vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'main.tex', line: 2 })
  const order: string[] = []
  const save = vi.spyOn(api, 'saveManuscriptFile').mockImplementation(async () => { order.push('save'); return saved() })
  vi.spyOn(api, 'compileManuscript').mockImplementation(async () => { order.push('compile'); return { state: 'queued' } })
  renderPage()
  const src = await screen.findByLabelText('LaTeX source')
  await waitFor(() => expect(src).toHaveValue('Intro line.\nWe study cats. Dogs bark.'))
  dbl('Dogs')
  const box = await editBox()
  expect(box).toHaveValue('Dogs bark.')
  fireEvent.change(box, { target: { value: 'Cats purr.' } })
  fireEvent.keyDown(box, { key: 'Enter' })
  await waitFor(() => expect(order).toEqual(['save', 'compile']))
  expect(save).toHaveBeenCalledWith('m1', 'main.tex', 'Intro line.\nWe study cats. Cats purr.', T2)
  expect(screen.getByLabelText('LaTeX source')).toHaveValue('Intro line.\nWe study cats. Cats purr.')
})

test('another file is saved through the API with its base, then compiled', async () => {
  withPdf()
  server['b.tex'] = { text: 'Bees hum loudly.', at: T3 }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'syncForward').mockRejectedValue(new Error('x'))
  vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'b.tex', line: 1 })
  const save = vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue({ path: 'b.tex', size: 1, updated_at: T4 })
  const compile = vi.spyOn(api, 'compileManuscript').mockResolvedValue({ state: 'queued' })
  renderPage()
  await screen.findByLabelText('LaTeX source')
  dbl('Bees')
  fireEvent.change(await editBox(), { target: { value: 'Bees buzz.' } })
  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edit this text' }), { key: 'Enter' })
  await waitFor(() => expect(compile).toHaveBeenCalled())
  expect(save).toHaveBeenCalledWith('m1', 'b.tex', 'Bees buzz.', T3)
})

test('a stale base shows the message and writes nothing', async () => {
  withPdf()
  server['b.tex'] = { text: 'Bees hum loudly.', at: T3 }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'syncForward').mockRejectedValue(new Error('x'))
  vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'b.tex', line: 1 })
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(conflict())
  const compile = vi.spyOn(api, 'compileManuscript').mockResolvedValue({ state: 'queued' })
  renderPage()
  await screen.findByLabelText('LaTeX source')
  dbl('Bees')
  await editBox()
  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edit this text' }), { key: 'Enter' })
  expect(await screen.findByText('This file changed since. Open it in the editor to edit it.')).toBeInTheDocument()
  expect(compile).not.toHaveBeenCalled()
})

test('text made by LaTeX offers Open in source and edits nothing', async () => {
  withPdf()
  server['main.tex'] = { text: 'See \\cite{smith}.', at: T2 }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'syncForward').mockRejectedValue(new Error('x'))
  vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'main.tex', line: 1 })
  const save = vi.spyOn(api, 'saveManuscriptFile')
  renderPage()
  await screen.findByLabelText('LaTeX source')
  dbl('[1]')
  expect(await screen.findByText(/This text is made by LaTeX/)).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: 'Edit this text' })).toBeNull()
  expect(save).not.toHaveBeenCalled()
})

test('a double-click answered after another file opened is dropped', async () => {
  withPdf()
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail())
  const late = deferred<{ file: string; line: number }>()
  vi.spyOn(api, 'syncInverse').mockReturnValue(late.promise)
  const view = renderPage()
  await screen.findByLabelText('LaTeX source')
  dbl('hello')
  view.open('b.tex')
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('bee'))
  await act(async () => { late.resolve({ file: 'main.tex', line: 1 }) })
  expect(screen.queryByRole('textbox', { name: 'Edit this text' })).toBeNull()
})

test('a second double-click on the same line opens its own sentence', async () => {
  withPdf()
  server['main.tex'] = { text: 'We study cats. Dogs bark.', at: T2 }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'syncForward').mockRejectedValue(new Error('x'))
  vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'main.tex', line: 1 })
  const save = vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  vi.spyOn(api, 'compileManuscript').mockResolvedValue({ state: 'queued' })
  renderPage()
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('We study cats. Dogs bark.'))
  dbl('cats')
  await waitFor(async () => expect(await editBox()).toHaveValue('We study cats.'))
  dbl('Dogs')
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Edit this text' })).toHaveValue('Dogs bark.'))
  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edit this text' }), { key: 'Enter' })
  await waitFor(() => expect(save).toHaveBeenCalledWith('m1', 'main.tex', 'We study cats. Dogs bark.', T2))
})

test('typing over the sentence after the box opened is refused and writes nothing', async () => {
  withPdf()
  server['main.tex'] = { text: 'Dogs bark.', at: T2 }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'syncForward').mockRejectedValue(new Error('x'))
  vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'main.tex', line: 1 })
  const compile = vi.spyOn(api, 'compileManuscript').mockResolvedValue({ state: 'queued' })
  renderPage()
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('Dogs bark.'))
  dbl('Dogs')
  await editBox()
  const save = vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  fireEvent.change(screen.getByLabelText('LaTeX source'), { target: { value: 'Dogs howl.' } })
  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edit this text' }), { key: 'Enter' })
  expect(await screen.findByText('This file changed since. Open it in the editor to edit it.')).toBeInTheDocument()
  expect(screen.getByLabelText('LaTeX source')).toHaveValue('Dogs howl.')
  expect(compile).not.toHaveBeenCalled()
  expect(save).not.toHaveBeenCalled()
})

test('when the editor cannot save, the box closes with a plain note and nothing compiles', async () => {
  withPdf()
  server['main.tex'] = { text: 'Dogs bark.', at: T2 }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'syncForward').mockRejectedValue(new Error('x'))
  vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'main.tex', line: 1 })
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new ApiError('bad_path', 400, { detail: 'bad_path' }))
  const compile = vi.spyOn(api, 'compileManuscript').mockResolvedValue({ state: 'queued' })
  renderPage()
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('Dogs bark.'))
  dbl('Dogs')
  fireEvent.change(await editBox(), { target: { value: 'Cats purr.' } })
  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edit this text' }), { key: 'Enter' })
  expect(await screen.findByText("Your change is in the editor but couldn't be saved yet. The editor shows why.")).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: 'Edit this text' })).toBeNull()
  expect(screen.getByLabelText('LaTeX source')).toHaveValue('Cats purr.')
  expect(compile).not.toHaveBeenCalled()
})

test('a spot in a file LaTeX wrote (main.bbl) shows the notice without Open in source, and ctrl-click stays put', async () => {
  withPdf()
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'syncForward').mockRejectedValue(new Error('x'))
  const inverse = vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'main.bbl', line: 3 })
  const save = vi.spyOn(api, 'saveManuscriptFile')
  renderPage()
  await screen.findByLabelText('LaTeX source')
  dbl('Smith')
  expect(await screen.findByText(/This text is made by LaTeX/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Open in source' })).toBeNull()
  expect(screen.queryByRole('textbox', { name: 'Edit this text' })).toBeNull()
  fireEvent.click(pages().querySelector('[data-page="2"]')!, { metaKey: true })
  await waitFor(() => expect(inverse).toHaveBeenCalledTimes(2))
  await new Promise((r) => setTimeout(r, 0))
  expect(window.location.hash).toBe('')
  expect(editor.current!.jumpTo?.line).not.toBe(3)
  expect(save).not.toHaveBeenCalled()
})

test('E on the PDF pages opens the box on the whole SyncTeX line at the visible centre', async () => {
  withPdf()
  server['main.tex'] = { text: 'Intro.\n\\section{Results} We found it. It works.\nEnd.', at: T2 }
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'syncForward').mockRejectedValue(new Error('x'))
  const inverse = vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'main.tex', line: 2 })
  renderPage()
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('Intro.\n\\section{Results} We found it. It works.\nEnd.'))
  fireEvent.keyDown(pages(), { key: 'e' })
  expect(await editBox()).toHaveValue('\\section{Results} We found it. It works.')
  expect(inverse).toHaveBeenCalledWith('m1', expect.any(Number), expect.any(Number), expect.any(Number))
})

test('a compile started by an edit from the PDF keeps the PDF where it is; the next compile follows the cursor', async () => {
  const docs = new Map<string | null, object>()
  pdf.mockImplementation((url: string | null) => {
    if (!docs.has(url)) docs.set(url, { numPages: 3 })
    return { doc: docs.get(url) as never, error: null }
  })
  server['main.tex'] = { text: 'Dogs bark.', at: T2 }
  const get = vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  const forward = vi.spyOn(api, 'syncForward').mockResolvedValue({ page: 2, x: 0, y: 300 })
  vi.spyOn(api, 'syncInverse').mockResolvedValue({ file: 'main.tex', line: 1 })
  vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  const compile = vi.spyOn(api, 'compileManuscript').mockResolvedValue({ state: 'queued' })
  renderPage()
  await waitFor(() => expect(forward).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(pages().scrollTop).toBeGreaterThan(0))
  fireEvent.wheel(pages())
  pages().scrollTop = 7 // the reader scrolled to the spot they edit
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('Dogs bark.'))
  get.mockResolvedValue(detail({ compile_status: 'ok', compiled_at: T4 }))
  dbl('Dogs')
  fireEvent.change(await editBox(), { target: { value: 'Cats purr.' } })
  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Edit this text' }), { key: 'Enter' })
  await waitFor(() => expect(compile).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(pdf).toHaveBeenLastCalledWith(expect.stringContaining(encodeURIComponent(T4))))
  await new Promise((r) => setTimeout(r, 0))
  expect(forward).toHaveBeenCalledTimes(1)
  expect(pages().scrollTop).toBe(7)
  // A compile from the editor follows the cursor again.
  get.mockResolvedValue(detail({ compile_status: 'ok', compiled_at: '2026-10-05T00:00:00Z' }))
  act(() => { fireEvent.keyDown(screen.getByLabelText('LaTeX source'), { key: 's', ctrlKey: true }) })
  await waitFor(() => expect(forward).toHaveBeenCalledTimes(2))
  await waitFor(() => expect(pages().scrollTop).toBeGreaterThan(7)) // placed again (jsdom rects are 0, so it adds up)
})

const widen = () => Object.defineProperty(window, 'innerWidth', { value: 1400, configurable: true }) // jsdom is 1024: narrow, so the deck would sit in a hidden tab
afterEach(() => Object.defineProperty(window, 'innerWidth', { value: 1024, configurable: true }))
const paper = { paper_id: 'pk', key: 'k1', pinned: false, title: 'Kappa paper', first_author: 'Kappa', year: 2021, has_pdf: true, notes: 0, highlights: 0, ai_notes: 0 }

test('inserting from the deck pins the paper, puts the cite in the open file and autosaves it', async () => {
  vi.spyOn(api, 'manuscriptPapers').mockResolvedValue([paper])
  vi.spyOn(api, 'listNotes').mockResolvedValue([])
  vi.spyOn(api, 'rankPapers').mockResolvedValue({ paper_ids: [] })
  const pin = vi.spyOn(api, 'pinPaper').mockResolvedValue({ key: 'k1' })
  const save = vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  widen()
  renderPage()
  const box = await screen.findByLabelText('LaTeX source')
  await waitFor(() => expect(box).toHaveValue('hello'))
  fireEvent.keyDown(await screen.findByRole('group', { name: 'Papers' }), { key: 'Enter' })
  fireEvent.click(await screen.findByText('Insert \\citep{k1}'))
  await waitFor(() => expect(box).toHaveValue('hello\\citep{k1}'))
  expect(pin).toHaveBeenCalledWith('m1', 'pk')
  await waitFor(() => expect(save).toHaveBeenCalledWith('m1', 'main.tex', 'hello\\citep{k1}', T2), { timeout: 3000 })
})

test('Mod+Alt+K on a cite key opens that paper in the deck, already open', async () => {
  vi.spyOn(api, 'manuscriptPapers').mockResolvedValue([paper])
  vi.spyOn(api, 'listNotes').mockResolvedValue([])
  vi.spyOn(api, 'rankPapers').mockResolvedValue({ paper_ids: [] })
  widen()
  renderPage()
  await screen.findByRole('group', { name: 'Papers' })
  act(() => editor.current!.onCiteKey!('k1'))
  expect(await screen.findByRole('group', { name: 'Kappa paper' })).toBeInTheDocument()
})

test('Cmd+K jumps to a label in another file, opens a paper in the deck, and runs commands', async () => {
  server['main.tex'].text = '\\section{Intro}\n\\input{b}'
  server['b.tex'].text = '\\section{Methods}\nsee \\label{tab:data}'
  vi.spyOn(api, 'manuscriptPapers').mockResolvedValue([paper])
  vi.spyOn(api, 'listNotes').mockResolvedValue([])
  vi.spyOn(api, 'rankPapers').mockResolvedValue({ paper_ids: [] })
  const compile = vi.spyOn(api, 'compileManuscript').mockResolvedValue({ state: 'queued' })
  Element.prototype.scrollIntoView = vi.fn() // jsdom has none; cmdk scrolls the active item
  const assign = vi.fn()
  vi.stubGlobal('location', { ...window.location, assign })
  widen()
  renderPage()
  const box = await screen.findByLabelText('LaTeX source')
  await waitFor(() => expect(box).toHaveValue('\\section{Intro}\n\\input{b}'))
  fireEvent.keyDown(box, { key: 'k', ctrlKey: true }) // from inside the editor
  const input = await screen.findByPlaceholderText(/Jump to a section/)
  fireEvent.change(input, { target: { value: 'tabdata' } })
  fireEvent.click(await screen.findByText('tab:data'))
  expect(assign).toHaveBeenCalledWith(expect.stringContaining('b.tex'))
  expect(assign.mock.calls[0][0]).toContain('line=2')
  await waitFor(() => expect(screen.queryByPlaceholderText(/Jump to a section/)).toBeNull())

  fireEvent.keyDown(document.body, { key: 'k', metaKey: true })
  fireEvent.change(await screen.findByPlaceholderText(/Jump to a section/), { target: { value: 'Kappa' } })
  fireEvent.click(within(await screen.findByRole('dialog')).getByText('Kappa paper'))
  expect(await screen.findByRole('group', { name: 'Kappa paper' })).toBeInTheDocument()

  fireEvent.keyDown(document.body, { key: 'k', ctrlKey: true })
  fireEvent.click(within(await screen.findByRole('dialog')).getByText('Compile'))
  await waitFor(() => expect(compile).toHaveBeenCalled())
})

test('palette: Show in PDF runs the forward lookup; it stays shut behind another dialog', async () => {
  Element.prototype.scrollIntoView = vi.fn()
  vi.spyOn(api, 'manuscriptPapers').mockResolvedValue([])
  const forward = vi.spyOn(api, 'syncForward').mockResolvedValue({ page: 1, x: 0, y: 0 })
  renderPage()
  const box = await screen.findByLabelText('LaTeX source')
  await waitFor(() => expect(box).toHaveValue('hello'))
  fireEvent.click(await screen.findByRole('button', { name: 'History' }))
  await screen.findByRole('dialog')
  fireEvent.keyDown(document.body, { key: 'k', ctrlKey: true })
  expect(screen.queryByPlaceholderText(/Jump to a section/)).toBeNull()
  fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  forward.mockClear()
  fireEvent.keyDown(document.body, { key: 'k', ctrlKey: true })
  fireEvent.click(within(await screen.findByRole('dialog')).getByText('Show in PDF'))
  await waitFor(() => expect(forward).toHaveBeenCalledWith('m1', 'main.tex', 1))
})

// Narrow (jsdom's 1024 px window): the PDF and the Papers share one column as two tabs.
afterEach(() => localStorage.removeItem('paperlab-studio-tab'))
const tab = (name: string) => screen.getByRole('tab', { name })

test('shared tabs: Mod+Alt+P and the palette\'s Show in PDF bring the PDF tab forward', async () => {
  Element.prototype.scrollIntoView = vi.fn()
  vi.spyOn(api, 'manuscriptPapers').mockResolvedValue([])
  const forward = vi.spyOn(api, 'syncForward').mockResolvedValue({ page: 1, x: 0, y: 0 })
  renderPage()
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello'))
  fireEvent.click(tab('Papers'))
  act(() => editor.current!.onShowInPdf!(1))
  expect(tab('PDF')).toHaveAttribute('aria-selected', 'true')
  await waitFor(() => expect(forward).toHaveBeenCalledWith('m1', 'main.tex', 1))
  fireEvent.click(tab('Papers'))
  fireEvent.keyDown(document.body, { key: 'k', ctrlKey: true })
  fireEvent.click(within(await screen.findByRole('dialog')).getByText('Show in PDF'))
  await waitFor(() => expect(tab('PDF')).toHaveAttribute('aria-selected', 'true'))
})

test('shared tabs: the PDF following a finished compile never takes the Papers tab away', async () => {
  withPdf()
  const get = vi.spyOn(api, 'getManuscript').mockResolvedValue(detail(GOOD))
  vi.spyOn(api, 'manuscriptPapers').mockResolvedValue([])
  vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  vi.spyOn(api, 'compileManuscript').mockResolvedValue({ state: 'queued' })
  const forward = vi.spyOn(api, 'syncForward').mockResolvedValue({ page: 1, x: 0, y: 0 })
  renderPage()
  await waitFor(() => expect(forward).toHaveBeenCalledTimes(1))
  fireEvent.click(tab('Papers'))
  get.mockResolvedValue(detail({ compile_status: 'ok', compiled_at: T4 }))
  ctrlS(await type('hello again'))
  await waitFor(() => expect(forward).toHaveBeenCalledTimes(2))
  expect(tab('Papers')).toHaveAttribute('aria-selected', 'true')
})
