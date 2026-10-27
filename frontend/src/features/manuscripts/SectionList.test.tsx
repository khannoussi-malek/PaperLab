// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { SectionList } from './SectionList'

const WORDS = Array.from({ length: 30 }, (_, i) => `word${i}`).join(' ')
const MAIN = '\\begin{document}\n\\input{sections/intro}\n\\input{sections/method.tex}\n\\input{sections/gone}\n\\end{document}'
const TEXTS = {
  'main.tex': MAIN,
  'sections/intro.tex': `\\section{Introduction}\n${WORDS}\n\\subsection{Motivation}\nx`,
  'sections/method.tex': '\\section{Method}\n% TODO fill',
}
const ITEMS = [
  { level: 1 as const, title: 'Introduction', file: 'sections/intro.tex', line: 1 },
  { level: 2 as const, title: 'Motivation', file: 'sections/intro.tex', line: 3 },
]

function setup(over: Partial<React.ComponentProps<typeof SectionList>> = {}) {
  const props = {
    manuscriptId: 'm1', main: 'main.tex', texts: TEXTS, filePaths: ['main.tex', 'sections/intro.tex', 'sections/method.tex'], errorsByFile: {}, current: { path: 'sections/intro.tex', line: 1 },
    items: ITEMS, onOpen: vi.fn(), onJump: vi.fn(), flushCurrent: vi.fn(async () => true), ...over,
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><SectionList {...props} /></QueryClientProvider>)
  return props
}
const row = (name: RegExp) => screen.getByRole('button', { name: new RegExp(`^\\d+\\s*${name.source}`) })

beforeEach(() => { window.location.hash = '' })
afterEach(() => { vi.restoreAllMocks(); window.location.hash = '' })

test('rows show number, title, word count and a text status', () => {
  setup({ errorsByFile: { 'sections/intro.tex': 2 } })
  const intro = row(/Introduction/)
  expect(intro).toHaveTextContent('1')
  expect(intro).toHaveTextContent('33 words')
  expect(intro).toHaveTextContent('2 compile errors')
  expect(row(/Method/)).toHaveTextContent('1 TODO')
  expect(row(/gone/)).toHaveTextContent('File missing')
})

test('the open section lists its subsections and they jump', () => {
  const p = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Motivation' }))
  expect(p.onJump).toHaveBeenCalledWith('sections/intro.tex', 3)
})

test('arrows move focus, Enter opens', () => {
  const p = setup()
  row(/Introduction/).focus()
  fireEvent.keyDown(row(/Introduction/), { key: 'ArrowDown' })
  expect(row(/Method/)).toHaveFocus()
  fireEvent.keyDown(row(/Method/), { key: 'Enter' })
  expect(p.onOpen).toHaveBeenCalledWith(expect.objectContaining({ path: 'sections/method.tex' }))
})

test('Alt+Down moves the section to index + 1, after saving the editor', async () => {
  const move = vi.spyOn(api, 'moveSection').mockResolvedValue(undefined)
  const p = setup()
  fireEvent.keyDown(row(/Introduction/), { key: 'ArrowDown', altKey: true })
  await waitFor(() => expect(move).toHaveBeenCalledWith('m1', 'sections/intro.tex', 1))
  expect(p.flushCurrent).toHaveBeenCalled()
})

test('every operation stops when the editor could not save', async () => {
  const move = vi.spyOn(api, 'moveSection').mockResolvedValue(undefined)
  const add = vi.spyOn(api, 'addSection').mockResolvedValue({ path: 'sections/x.tex' })
  const p = setup({ flushCurrent: vi.fn(async () => false) })
  fireEvent.keyDown(row(/Introduction/), { key: 'ArrowDown', altKey: true })
  fireEvent.keyDown(row(/Introduction/), { key: 'n' })
  fireEvent.change(await screen.findByLabelText('Section title'), { target: { value: 'X' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))
  await waitFor(() => expect(p.flushCurrent).toHaveBeenCalledTimes(2))
  expect(move).not.toHaveBeenCalled()
  expect(add).not.toHaveBeenCalled()
})

test('N adds a section after the focused one and opens it', async () => {
  const add = vi.spyOn(api, 'addSection').mockResolvedValue({ path: 'sections/results.tex' })
  setup()
  fireEvent.keyDown(row(/Introduction/), { key: 'N' })
  fireEvent.change(await screen.findByLabelText('Section title'), { target: { value: 'Results' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))
  await waitFor(() => expect(add).toHaveBeenCalledWith('m1', 'Results', 'sections/intro.tex'))
  await waitFor(() => expect(window.location.hash).toBe('#/manuscripts/m1?file=sections%2Fresults.tex'))
})

test('F2 renames and opens the new path', async () => {
  const retitle = vi.spyOn(api, 'retitleSection').mockResolvedValue({ path: 'sections/background.tex' })
  setup()
  fireEvent.keyDown(row(/Introduction/), { key: 'F2' })
  expect(await screen.findByLabelText('Section title')).toHaveValue('Introduction')
  fireEvent.change(screen.getByLabelText('Section title'), { target: { value: 'Background' } })
  fireEvent.click(screen.getByRole('button', { name: 'Rename' }))
  await waitFor(() => expect(retitle).toHaveBeenCalledWith('m1', 'sections/intro.tex', 'Background'))
  await waitFor(() => expect(window.location.hash).toContain('background.tex'))
})

test('Delete asks, naming the file, then deletes', async () => {
  const del = vi.spyOn(api, 'deleteSection').mockResolvedValue(undefined)
  setup()
  fireEvent.keyDown(row(/Method/), { key: 'Delete' })
  expect(await screen.findByText('Delete sections/method.tex?')).toBeInTheDocument()
  expect(del).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(del).toHaveBeenCalledWith('m1', 'sections/method.tex'))
})

test('Backspace (the Mac Delete key) asks too', async () => {
  const del = vi.spyOn(api, 'deleteSection').mockResolvedValue(undefined)
  setup()
  fireEvent.keyDown(row(/Method/), { key: 'Backspace' })
  expect(await screen.findByText('Delete sections/method.tex?')).toBeInTheDocument()
  expect(del).not.toHaveBeenCalled()
})

test('the row menu has Move up and Move down', async () => {
  const move = vi.spyOn(api, 'moveSection').mockResolvedValue(undefined)
  setup()
  fireEvent.keyDown(screen.getByRole('button', { name: 'Actions for Method' }), { key: 'Enter' })
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Move up' }))
  await waitFor(() => expect(move).toHaveBeenCalledWith('m1', 'sections/method.tex', 0))
})

test('Split into files shows only for single-file manuscripts', async () => {
  const split = vi.spyOn(api, 'splitSections').mockResolvedValue({ paths: [] })
  const { unmount } = (() => { setup(); return { unmount: () => document.body.replaceChildren() } })()
  expect(screen.queryByRole('button', { name: 'Split into files' })).toBeNull()
  unmount()
  setup({ texts: { 'main.tex': '\\section{One}\nx\n\\section{Two}\ny' }, current: { path: 'main.tex', line: 1 } })
  fireEvent.click(screen.getByRole('button', { name: 'Split into files' }))
  await waitFor(() => expect(split).toHaveBeenCalledWith('m1'))
})

test('a section whose text is still loading is not called missing', () => {
  const { 'sections/method.tex': _m, ...loaded } = TEXTS
  setup({ texts: loaded })
  expect(row(/method/)).toHaveTextContent('Loading')
  expect(row(/method/)).not.toHaveTextContent('File missing')
  expect(row(/gone/)).toHaveTextContent('File missing')
})

test('no empty state before main.tex has loaded', () => {
  setup({ texts: {} })
  expect(screen.queryByText(/No sections yet/)).toBeNull()
  expect(screen.getByText('Loading sections…')).toBeInTheDocument()
})

test('a refused move does not leave focus to be stolen by a later one', async () => {
  const move = vi.spyOn(api, 'moveSection').mockRejectedValueOnce(new Error('boom')).mockResolvedValue(undefined)
  setup()
  fireEvent.keyDown(row(/Introduction/), { key: 'ArrowDown', altKey: true })
  await waitFor(() => expect(move).toHaveBeenCalledTimes(1))
  row(/Method/).focus()
  fireEvent.keyDown(row(/Method/), { key: 'ArrowUp', altKey: true })
  await waitFor(() => expect(move).toHaveBeenCalledTimes(2))
  await new Promise((r) => setTimeout(r, 20))
  expect(row(/Introduction/)).not.toHaveFocus()
})

test('a double Delete sends one request', async () => {
  const del = vi.spyOn(api, 'deleteSection').mockResolvedValue(undefined)
  setup()
  fireEvent.keyDown(row(/Method/), { key: 'Delete' })
  const btn = await screen.findByRole('button', { name: 'Delete' })
  fireEvent.click(btn)
  fireEvent.click(btn)
  await waitFor(() => expect(del).toHaveBeenCalled())
  expect(del).toHaveBeenCalledTimes(1)
})

const single = { 'main.tex': '\\section{One}\nx\n\\section{Two}\ny' }
function mountWith(request: { kind: 'new' | 'split'; n: number }, over: Partial<React.ComponentProps<typeof SectionList>> = {}) {
  const props = {
    manuscriptId: 'm1', main: 'main.tex', texts: single, filePaths: ['main.tex'], errorsByFile: {}, current: { path: 'main.tex', line: 1 },
    items: [], onOpen: vi.fn(), onJump: vi.fn(), flushCurrent: vi.fn(async () => true) as ReturnType<typeof vi.fn> & (() => Promise<boolean>), ...over,
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const ui = (r: typeof request) => <QueryClientProvider client={client}><SectionList {...props} request={r} /></QueryClientProvider>
  const view = render(ui(request))
  return { props, ask: (r: typeof request) => view.rerender(ui(r)) }
}

test('a request made before the list mounted is not replayed; a later one is, after saving', async () => {
  const split = vi.spyOn(api, 'splitSections').mockResolvedValue({ paths: [] })
  const { props, ask } = mountWith({ kind: 'split', n: 3 })
  await new Promise((r) => setTimeout(r, 0))
  expect(props.flushCurrent).not.toHaveBeenCalled()
  expect(split).not.toHaveBeenCalled()
  ask({ kind: 'split', n: 4 })
  await waitFor(() => expect(split).toHaveBeenCalledWith('m1'))
  expect(vi.mocked(props.flushCurrent).mock.invocationCallOrder[0]).toBeLessThan(split.mock.invocationCallOrder[0])
})

test('a new-section request opens the New section dialog', async () => {
  const { ask } = mountWith({ kind: 'new', n: 1 })
  expect(screen.queryByRole('dialog')).toBeNull()
  ask({ kind: 'new', n: 2 })
  expect(await screen.findByRole('dialog')).toHaveTextContent('New section')
})
