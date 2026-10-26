// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, type ManuscriptDetail } from '@/api/client'
import { keptTexts } from './keptTexts'
import { ManuscriptPage } from './ManuscriptPage'

const pdf = vi.hoisted(() => vi.fn((_url: string | null) => ({ doc: null, error: null })))
// jsdom can't lay CodeMirror out, so here the editor is a textarea with the same props (LatexEditor.test.tsx runs the real one).
vi.mock('./LatexEditor', () => ({
  LatexEditor: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <textarea aria-label="LaTeX source" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}))
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
