// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, ApiError, type CitablePaper, type EvidenceFound, type EvidenceRow } from '@/api/client'

vi.mock('../../graph/hands/HandsMode', () => ({ default: () => null }))
import { DeckColumn } from './DeckColumn'

const mk = (id: string, title: string): CitablePaper => ({
  paper_id: `p${id}`, key: `${id}1`, pinned: false, title, first_author: title, year: 2020, has_pdf: true, notes: 0, highlights: 0, ai_notes: 0,
})
const papers = [mk('a', 'Alpha'), mk('b', 'Beta'), mk('c', 'Gamma')]
const found = (over: Partial<EvidenceFound> = {}): EvidenceFound => ({
  sentence_hash: 'h1',
  verdicts: 'queued',
  papers: [
    { paper_id: 'pc', key: 'c1', passages: [{ chunk_id: 'k2', page: 5, text: 'Later passage' }, { chunk_id: 'k1', page: 2, text: 'Early passage' }] },
    { paper_id: 'pb', key: 'b1', passages: [{ chunk_id: 'k3', page: 1, text: 'Beta passage' }] },
  ],
  ...over,
})
const row = (paper_id: string, over: Partial<EvidenceRow> = {}): EvidenceRow =>
  ({ paper_id, rank: 0, status: 'queued', verdict: null, reason: null, quote: null, page: null, output_id: null, ...over }) as EvidenceRow

let find: ReturnType<typeof vi.spyOn>
let rows: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.spyOn(api, 'manuscriptPapers').mockResolvedValue(papers)
  vi.spyOn(api, 'listNotes').mockResolvedValue([])
  vi.spyOn(api, 'rankPapers').mockResolvedValue({ paper_ids: [] })
  vi.spyOn(api, 'pinPaper').mockImplementation(async (_m, p) => ({ key: `${p.slice(1)}1` }))
  find = vi.spyOn(api, 'findEvidence').mockResolvedValue(found())
  rows = vi.spyOn(api, 'evidenceRows').mockResolvedValue([row('pc'), row('pb')])
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

function setup() {
  const props = { manuscriptId: 'm1', sectionKey: 's', sectionText: 'x', allTexts: ['x'], onInsert: vi.fn(() => true), openKey: null, onFindEvidence: vi.fn(() => true) }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (ask: { doc: string; from: number; to: number; n: number } | null) => (
    <QueryClientProvider client={client}><DeckColumn {...props} evidenceAsk={ask} /></QueryClientProvider>
  )
  const view = render(ui(null))
  const ask = (doc = 'Cats purr. Dogs bark.', at = 2, n = 1) => view.rerender(ui({ doc, from: at, to: at, n }))
  return { props, ask, view }
}
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const status = () => screen.getAllByRole('status').map((s) => s.textContent).join(' | ')

it('shows the sentence, puts papers with evidence first in rank order, and badges the cards', async () => {
  const { ask } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  expect(await screen.findByText(/Evidence for:/)).toHaveTextContent('Evidence for: ‘Cats purr.’')
  expect(find).toHaveBeenCalledWith('m1', 'Cats purr.')
  await waitFor(() => expect(status()).toContain('Gamma 2020, evidence 2, Checking…, paper 1 of 3'))
  fireEvent.keyDown(screen.getByRole('group', { name: 'Papers' }), { key: 'ArrowRight' })
  expect(status()).toContain('Beta 2020, evidence 1')
  expect(document.body.textContent).toContain('E 2')
})

it('polls every 2 seconds while a check is queued or running and then shows the verdict', async () => {
  const { ask } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  await screen.findByText(/Evidence for:/)
  await waitFor(() => expect(rows).toHaveBeenCalledTimes(1))
  rows.mockResolvedValue([row('pc', { status: 'done', verdict: 'supported', reason: 'It says so', quote: 'Cats do purr', page: 2 }), row('pb', { status: 'running' })])
  await tick(2100)
  await waitFor(() => expect(status()).toContain('Gamma 2020, evidence 2, Supports'))
  const calls = rows.mock.calls.length
  rows.mockResolvedValue([row('pc', { status: 'done', verdict: 'supported' }), row('pb', { status: 'done', verdict: 'not_addressed' })])
  await tick(2100)
  await waitFor(() => expect(rows.mock.calls.length).toBeGreaterThan(calls))
  const done = rows.mock.calls.length
  await tick(6000)
  expect(rows.mock.calls.length).toBe(done) // all finished: it stops by itself
})

it('Clear (button or Esc) leaves evidence mode and stops polling', async () => {
  const { ask } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  await screen.findByText(/Evidence for:/)
  await waitFor(() => expect(rows).toHaveBeenCalled())
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
  expect(screen.queryByText(/Evidence for:/)).toBeNull()
  await tick(500)
  const n = rows.mock.calls.length
  await tick(6000)
  expect(rows.mock.calls.length).toBe(n)
  ask('Cats purr.', 2, 2)
  await screen.findByText(/Evidence for:/)
  fireEvent.keyDown(screen.getByRole('group', { name: 'Papers' }), { key: 'Escape' })
  expect(screen.queryByText(/Evidence for:/)).toBeNull()
})

it('a new ask stops the old polling', async () => {
  const { ask } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  await screen.findByText(/Evidence for:/)
  find.mockResolvedValue(found({ sentence_hash: 'h2' }))
  ask('Cats purr. Dogs bark.', 14, 2)
  await waitFor(() => expect(rows).toHaveBeenCalledWith('m1', 'h2'))
  rows.mockClear()
  await tick(2100)
  expect(rows.mock.calls.every((c: unknown[]) => c[1] === 'h2')).toBe(true)
})

it('leaving the manuscript stops the polling', async () => {
  const { ask, view } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  await screen.findByText(/Evidence for:/)
  await waitFor(() => expect(rows).toHaveBeenCalled())
  view.unmount()
  const n = rows.mock.calls.length
  await tick(6000)
  expect(rows.mock.calls.length).toBe(n)
})

it.each([
  ['no_workspace', "This manuscript isn't in a workspace, so there are no papers to search."],
  ['empty_claim', 'Put the cursor in a sentence first.'],
  ['claim_too_long', "That's too long to check. Select one sentence."],
])('says %s inline in the header', async (code, text) => {
  find.mockRejectedValue(new ApiError(code, 422, { detail: code }))
  const { ask } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  expect(await screen.findByText(text)).toBeTruthy()
})

it('an empty spot in the text asks for a sentence without calling the server', async () => {
  const { ask } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask('   ', 1)
  expect(await screen.findByText('Put the cursor in a sentence first.')).toBeTruthy()
  expect(find).not.toHaveBeenCalled()
})

it('with no model, passages still show and the header says to add one', async () => {
  find.mockResolvedValue(found({ verdicts: 'unavailable' }))
  const { ask } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  expect(await screen.findByText('Add a model in Settings to get verdicts')).toBeTruthy()
  expect(rows).not.toHaveBeenCalled()
})

it('an open paper has blue E tabs in page order; inserting one gives only the citation; the reader opens at the passage', async () => {
  rows.mockResolvedValue([row('pc', { status: 'done', verdict: 'partially_supported', reason: 'Only in mice', quote: 'In mice', page: 2 }), row('pb')])
  const { ask, props } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  await screen.findByText(/Evidence for:/)
  fireEvent.keyDown(screen.getByRole('group', { name: 'Papers' }), { key: 'Enter' }) // Gamma, the first with evidence
  await screen.findByRole('group', { name: 'Gamma' })
  const tabs = screen.getAllByRole('button', { name: /^Evidence passage/ }).filter((b) => b.hasAttribute('data-book-tab'))
  expect(tabs.map((t) => t.getAttribute('aria-label'))).toEqual(['Evidence passage, page 2', 'Evidence passage, page 5'])
  expect(tabs[0].className).toContain('bg-blue')
  expect(await screen.findByText('Partly supports')).toBeTruthy()
  expect(screen.getByText('Only in mice')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Cite this paper' }))
  await waitFor(() => expect(props.onInsert).toHaveBeenCalledWith('\\citep{c1}'))
  const open = vi.spyOn(window, 'open').mockReturnValue(null)
  fireEvent.click(screen.getByRole('button', { name: 'Open in reader' }))
  expect(open).toHaveBeenCalledWith('#/papers/pc?chunk=k1&page=2', '_blank', 'noopener')
})

it('a Find evidence button on the deck asks the editor, and says so when there is no cursor yet', async () => {
  const { props } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  fireEvent.click(screen.getByRole('button', { name: 'Find evidence' }))
  expect(props.onFindEvidence).toHaveBeenCalledTimes(1)
  expect(screen.queryByText('Put the cursor in a sentence first.')).toBeNull()
  props.onFindEvidence.mockReturnValue(false)
  fireEvent.click(screen.getByRole('button', { name: 'Find evidence' }))
  expect(await screen.findByText('Put the cursor in a sentence first.')).toBeTruthy()
})

it('Mod+E in the deck does the same, and takes the key', async () => {
  const { props } = setup()
  const deck = await screen.findByRole('group', { name: 'Papers' })
  expect(fireEvent.keyDown(deck, { key: 'e', ctrlKey: true })).toBe(false) // default prevented
  expect(props.onFindEvidence).toHaveBeenCalledTimes(1)
  fireEvent.keyDown(deck, { key: 'e' })
  expect(props.onFindEvidence).toHaveBeenCalledTimes(1)
})

it('stops polling when the verdicts cannot be loaded, says so, and Retry loads them again', async () => {
  rows.mockRejectedValue(new Error('boom'))
  const { ask } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  expect(await screen.findByText("Couldn't load the verdicts.")).toBeTruthy()
  const calls = rows.mock.calls.length
  await tick(6000)
  expect(rows.mock.calls.length).toBe(calls)
  rows.mockResolvedValue([row('pc', { status: 'done', verdict: 'supported', reason: 'ok', quote: 'q', page: 2 }), row('pb')])
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await waitFor(() => expect(screen.queryByText("Couldn't load the verdicts.")).toBeNull())
  expect(rows.mock.calls.length).toBeGreaterThan(calls)
})

it('an open book goes back to its first item when the evidence passages change', async () => {
  const { ask } = setup()
  await screen.findByRole('group', { name: 'Papers' })
  ask()
  await screen.findByText(/Evidence for:/)
  fireEvent.keyDown(screen.getByRole('group', { name: 'Papers' }), { key: 'Enter' })
  await screen.findByRole('group', { name: 'Gamma' })
  const current = () => document.querySelector('[data-book-tab][aria-current=true]')?.getAttribute('aria-label')
  fireEvent.keyDown(screen.getByRole('group', { name: 'Gamma' }), { key: 'ArrowDown' })
  await waitFor(() => expect(current()).toBe('Evidence passage, page 5'))
  find.mockResolvedValue(found({ sentence_hash: 'h2', papers: [{ paper_id: 'pc', key: 'c1', passages: [{ chunk_id: 'k9', page: 8, text: 'New one' }, { chunk_id: 'k8', page: 9, text: 'New two' }] }] }))
  ask('Cats purr. Dogs bark.', 2, 2)
  await waitFor(() => expect(current()).toBe('Evidence passage, page 8'))
})
