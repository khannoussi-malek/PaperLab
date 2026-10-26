// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

test('shows the friendly message the worker stored', async () => {
  vi.spyOn(api, 'getManuscript').mockResolvedValue(
    detail({ compile_status: 'failed', compile_friendly: 'needs_download', compile_log: '', compiled_at: T3 }),
  )
  renderPage()
  expect(await screen.findByRole('alert')).toHaveTextContent('LaTeX needs to download packages once. Connect to the internet and compile again.')
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
  keptTexts.set('m1', 'main.tex', { text: 'mine', reason: 'error', base: T2 })
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
  await waitFor(() => expect(keptTexts.get('m1', 'main.tex')).toMatchObject({ text: 'hello world', base: T2 }))
  const second = renderPage('b.tex')
  expect(await screen.findByRole('link', { name: 'Open it' })).toHaveAttribute('href', '#/manuscripts/m1?file=main.tex')
  second.open('main.tex')
  await waitFor(() => expect(screen.getByLabelText('LaTeX source')).toHaveValue('hello world'))
})

test('kept text is dropped once it is saved', async () => {
  keptTexts.set('m1', 'main.tex', { text: 'mine', reason: 'error', base: T2 })
  vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(saved())
  renderPage()
  await screen.findByText('Unsaved changes')
  await waitFor(() => expect(keptTexts.get('m1', 'main.tex')).toBeUndefined(), { timeout: 3000 })
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
