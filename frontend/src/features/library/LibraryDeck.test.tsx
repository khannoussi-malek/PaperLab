// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'

const hm = vi.hoisted(() => ({ props: null as null | Record<string, (...a: never[]) => void> }))
vi.mock('../graph/hands/HandsMode', () => ({ default: (p: never) => { hm.props = p; return null } }))
import { LibraryDeck } from './LibraryDeck'

const mk = (id: string, title: string, over: Partial<Paper> = {}) =>
  ({ id: `p${id}`, title, authors: [title], year: 2020, has_pdf: true, ...over }) as Paper
const papers = [mk('a', 'Alpha'), mk('b', 'Beta'), mk('c', 'Gamma')]
const note = (id: string, body: string, over: Record<string, unknown> = {}) =>
  ({ id, body, provenance: 'human', anchors: [], paper_ids: ['pa'], ...over })

let counts: ReturnType<typeof vi.spyOn>
let open: ReturnType<typeof vi.fn>
beforeEach(() => {
  counts = vi.spyOn(api, 'noteCounts').mockResolvedValue({ pa: { notes: 2, highlights: 1, ai_notes: 0 } })
  vi.spyOn(api, 'listNotes').mockResolvedValue([
    note('n1', 'my thought') as never,
    note('n2', 'AI says', { provenance: 'llm' }) as never,
    note('n3', 'hl', { anchors: [{ paper_id: 'pa', page: 4, quoted_text: 'quoted bit' }] }) as never,
  ])
  open = vi.fn()
  vi.stubGlobal('open', open)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

function setup(list: Paper[] = papers) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><LibraryDeck papers={list} /></QueryClientProvider>)
}
const deck = () => screen.findByRole('group', { name: 'Papers' })
const status = () => screen.getAllByRole('status').map((s) => s.textContent).join(' | ')

it('opens on the first paper in the given order, with one counts request and badges', async () => {
  setup()
  await deck()
  await waitFor(() => expect(status()).toContain('Alpha 2020, 2 notes, 1 highlight, paper 1 of 3'))
  expect(counts).toHaveBeenCalledTimes(1)
  expect(counts).toHaveBeenCalledWith(['pa', 'pb', 'pc'])
})

it('only ~7 cards are in the DOM for 500 papers, with one counts request', async () => {
  const many = Array.from({ length: 500 }, (_, i) => mk(String(i), `Paper ${i}`))
  setup(many)
  await deck()
  expect(document.querySelectorAll('[data-deck-card]').length).toBeLessThanOrEqual(7)
  expect(counts).toHaveBeenCalledTimes(1)
  expect(counts.mock.calls[0][0]).toHaveLength(500)
})

it('renders papers without authors, year, pdf or notes in the deck and the book', async () => {
  vi.mocked(api.listNotes).mockResolvedValue([])
  setup([mk('x', 'Bare', { authors: [], year: null, has_pdf: false })])
  fireEvent.keyDown(await deck(), { key: 'Enter' })
  expect(await screen.findByRole('group', { name: 'Bare' })).toBeTruthy()
  expect(screen.getAllByText('No notes on this paper yet').length).toBeGreaterThan(0)
})

it('an open paper shows its notes and highlights, with no insert buttons, and ignores i', async () => {
  setup()
  fireEvent.keyDown(await deck(), { key: 'Enter' })
  const book = await screen.findByRole('group', { name: 'Alpha' })
  expect(screen.getByText('my thought')).toBeTruthy()
  expect(screen.getByText('quoted bit')).toBeTruthy()
  expect(screen.getByText('AI says')).toBeTruthy()
  expect(screen.queryByText(/Insert/)).toBeNull()
  expect(fireEvent.keyDown(book, { key: 'i' })).toBe(true)
  expect(open).not.toHaveBeenCalled()
  expect(document.body.textContent).not.toContain('\\citep')
  expect(document.querySelectorAll('[draggable="true"]')).toHaveLength(0)
})

it('Open in reader opens a new tab: the paper, or the selected note', async () => {
  setup()
  fireEvent.keyDown(await deck(), { key: 'Enter' })
  const book = await screen.findByRole('group', { name: 'Alpha' })
  fireEvent.keyDown(book, { key: 'o' })
  expect(open).toHaveBeenLastCalledWith(expect.stringMatching(/^#\/papers\/pa\?note=/), '_blank', 'noopener')
  fireEvent.click(screen.getByText('Open in reader'))
  expect(open).toHaveBeenCalledTimes(2)
})

it('keys: arrows flip with a live-region announcement, Esc in the book returns to the deck', async () => {
  setup()
  const d = await deck()
  fireEvent.keyDown(d, { key: 'ArrowRight' })
  expect(status()).toContain('Beta 2020')
  expect(status()).toContain('paper 2 of 3')
  fireEvent.keyDown(d, { key: 'Enter' })
  fireEvent.keyDown(await screen.findByRole('group', { name: 'Beta' }), { key: 'Escape' })
  expect(await deck()).toBeTruthy()
})

it('keeps your place when the list is reordered', async () => {
  const view = setup()
  fireEvent.keyDown(await deck(), { key: 'ArrowRight' })
  const client = new QueryClient()
  view.rerender(<QueryClientProvider client={client}><LibraryDeck papers={[papers[0], papers[2], papers[1]]} /></QueryClientProvider>)
  expect(status()).toContain('Beta 2020')
  expect(status()).toContain('paper 3 of 3')
})

it('the deck has no search box of its own and no drag handles or cite keys', async () => {
  setup()
  await deck()
  expect(screen.queryByRole('searchbox')).toBeNull()
  expect(document.querySelectorAll('[draggable="true"]')).toHaveLength(0)
})

it('keeps the badges while the counts for a changed list load', async () => {
  const view = setup()
  await waitFor(() => expect(status()).toContain('2 notes'))
  counts.mockReturnValue(new Promise(() => {}))
  const client = new QueryClient()
  view.rerender(<QueryClientProvider client={client}><LibraryDeck papers={[papers[0], papers[1]]} /></QueryClientProvider>)
  expect(status()).toContain('2 notes')
})

it('closes the open book and refocuses the deck when the search hides that paper', async () => {
  const view = setup()
  fireEvent.keyDown(await deck(), { key: 'Enter' })
  await screen.findByRole('group', { name: 'Alpha' })
  const client = new QueryClient()
  view.rerender(<QueryClientProvider client={client}><LibraryDeck papers={[papers[1], papers[2]]} /></QueryClientProvider>)
  const d = await deck()
  await waitFor(() => expect(document.activeElement).toBe(d))
  view.rerender(<QueryClientProvider client={client}><LibraryDeck papers={papers} /></QueryClientProvider>)
  expect(screen.queryByRole('group', { name: 'Alpha' })).toBeNull() // it does not reopen when the paper returns
})

it('a Hands close gesture closes the book and refocuses the deck', async () => {
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Hands' }))
  fireEvent.keyDown(await deck(), { key: 'Enter' })
  await screen.findByRole('group', { name: 'Alpha' })
  act(() => hm.props!.onZoom(0.01 as never)) // both hands together
  const d = await deck()
  await waitFor(() => expect(document.activeElement).toBe(d))
})
