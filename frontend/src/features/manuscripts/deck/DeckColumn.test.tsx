// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type CitablePaper } from '@/api/client'
import { DeckColumn } from './DeckColumn'

const mk = (id: string, title: string, over: Partial<CitablePaper> = {}): CitablePaper => ({
  paper_id: `p${id}`, key: `${id}1`, pinned: false, title, first_author: title, year: 2020, has_pdf: true, notes: 0, highlights: 0, ai_notes: 0, ...over,
})
const papers = [mk('a', 'Alpha'), mk('b', 'Beta'), mk('c', 'Gamma')]

let rank: ReturnType<typeof vi.spyOn>
let pin: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  vi.spyOn(api, 'manuscriptPapers').mockResolvedValue(papers)
  vi.spyOn(api, 'listNotes').mockResolvedValue([])
  pin = vi.spyOn(api, 'pinPaper').mockImplementation(async (_m, p) => ({ key: `${p.slice(1)}1` }))
  rank = vi.spyOn(api, 'rankPapers').mockResolvedValue({ paper_ids: ['pa', 'pb', 'pc'] })
})
afterEach(() => vi.restoreAllMocks())

type Over = Partial<React.ComponentProps<typeof DeckColumn>>
function setup(over: Over = {}) {
  const props = { manuscriptId: 'm1', sectionKey: 'intro', sectionText: 'We cite \\citep{c1}.', allTexts: ['We cite \\citep{c1}.', 'Later \\cite{b1}'], onInsert: vi.fn(() => true), openKey: null, ...over }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (p: typeof props) => <QueryClientProvider client={client}><DeckColumn {...p} /></QueryClientProvider>
  const view = render(ui(props))
  return { props, again: (o: Over) => view.rerender(ui({ ...props, ...o })) }
}
const deck = () => screen.findByRole('group', { name: 'Papers' })
const status = () => screen.getAllByRole('status').map((s) => s.textContent).join(' | ')

it('orders the deck: cited in this section, cited elsewhere, then the rest', async () => {
  setup()
  await deck()
  expect(status()).toContain('Gamma 2020, cited, paper 1 of 3')
  fireEvent.keyDown(await deck(), { key: 'ArrowRight' })
  expect(status()).toContain('Beta 2020, cited, paper 2 of 3')
})

it('inserting pins the paper first, then inserts at the editor', async () => {
  const { props } = setup()
  fireEvent.keyDown(await deck(), { key: 'Enter' }) // opens Gamma
  fireEvent.click(await screen.findByText('Insert \\citep{c1}'))
  await waitFor(() => expect(props.onInsert).toHaveBeenCalledWith('\\citep{c1}'))
  expect(pin).toHaveBeenCalledWith('m1', 'pc')
})

it('says so when there is no open file to insert into', async () => {
  setup({ onInsert: vi.fn(() => false) })
  fireEvent.keyDown(await deck(), { key: 'Enter' })
  fireEvent.click(await screen.findByText('Insert \\citep{c1}'))
  expect(await screen.findByText(/Open a file in the editor/)).toBeTruthy()
})

it('does not insert when the paper cannot be pinned', async () => {
  pin.mockRejectedValue(new Error('nope'))
  const { props } = setup()
  fireEvent.keyDown(await deck(), { key: 'Enter' })
  fireEvent.click(await screen.findByText('Insert \\citep{c1}'))
  expect(await screen.findByText(/nope/)).toBeTruthy()
  expect(props.onInsert).not.toHaveBeenCalled()
})

it('ranks once per section opened, not per keystroke, and ignores a failure', async () => {
  const { again } = setup()
  await waitFor(() => expect(rank).toHaveBeenCalledWith('m1', 'We cite \\citep{c1}.'), { timeout: 2000 })
  again({ sectionText: 'We cite \\citep{c1}. And more typing' })
  await act(() => new Promise((r) => setTimeout(r, 700)))
  expect(rank).toHaveBeenCalledTimes(1)
  rank.mockRejectedValue(new Error('offline'))
  again({ sectionKey: 'methods', sectionText: 'Methods' })
  await waitFor(() => expect(rank).toHaveBeenCalledTimes(2), { timeout: 2000 })
  expect(await deck()).toBeTruthy() // still fine
})

it('Mod+Alt+K (openKey) opens that paper in the deck, already open', async () => {
  const { again } = setup()
  await deck()
  again({ openKey: { key: 'a1', n: 1 } })
  expect(await screen.findByRole('group', { name: 'Alpha' })).toHaveAttribute('aria-roledescription', 'paper book')
})

it('a key that is not in the library says so', async () => {
  const { again } = setup()
  await deck()
  again({ openKey: { key: 'zzz', n: 1 } })
  expect(await screen.findByText(/zzz/)).toBeTruthy()
})

it('has a Hands toggle, off by default, that says the camera stays on this computer', async () => {
  setup()
  await deck()
  const toggle = screen.getByRole('button', { name: 'Hands' })
  expect(toggle).toHaveAttribute('aria-pressed', 'false')
  expect(screen.queryByText('The camera picture stays on this computer.')).toBeNull()
  fireEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText('The camera picture stays on this computer.')).toBeInTheDocument()
})
