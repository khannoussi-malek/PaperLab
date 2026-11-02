// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'
vi.mock('./pdfCache', () => ({ useCachedPdf: () => ({ doc: null, error: null }), retainOnly: vi.fn(), prefetchPdf: vi.fn() }))
vi.mock('../reader/PdfPage', () => ({ PdfPage: () => null }))
import { TriageDesk } from './TriageDesk'

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  Element.prototype.scrollIntoView = () => {}
  Element.prototype.hasPointerCapture = () => false
})
let decide: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  let n = 0
  decide = vi.spyOn(api, 'decideTriage').mockImplementation((async () => ({ event: { id: `e${++n}` } })) as never)
  vi.spyOn(api, 'undoTriage').mockResolvedValue({} as never)
  vi.spyOn(api, 'triageSummary').mockResolvedValue({ per_pile: {}, skipped: 0, card_ms: 0, pdf_opened: 0, decided: 0 } as never)
  vi.spyOn(api, 'paperSections').mockReturnValue(new Promise(() => {}) as never)
})
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear(); vi.restoreAllMocks() })

const mk = (id: string, title: string) =>
  ({ id, title, authors: [], year: null, status: 'ready', has_pdf: true, reading_pass: null, triage: null, created_at: `2026-01-0${id}T00:00:00Z` }) as unknown as Paper
const base = [mk('1', 'Old one'), mk('2', 'Middle'), mk('3', 'New one')]

function setup() {
  const onExit = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TriageDesk papers={base} library={base} scope="library" sourceLabel="your library" filterKey="" onExit={onExit} onShowKept={vi.fn()} />
    </QueryClientProvider>,
  )
  return { onExit, root: screen.getByRole('group', { name: 'Triage' }) }
}
const key = (el: Element, k: string) => fireEvent.keyDown(el, { key: k })
const title = () => screen.getByRole('heading', { level: 2 }).textContent
const toggle = () => screen.getByRole('button', { name: /First pass: five Cs/ })
const boxes = () => screen.queryAllByRole('checkbox')
const ticks = () => boxes().map((b) => b.getAttribute('aria-checked') === 'true')
const sent = async (i = 0) => {
  await waitFor(() => expect(decide.mock.calls.length).toBeGreaterThan(i))
  return decide.mock.calls[i][1] as { fivecs?: number | null; pile: string; reason?: string }
}
const live = () => document.querySelector('[aria-live="polite"]')!.textContent

it('is collapsed by default, and a decision never touched by it sends no fivecs', async () => {
  const { root } = setup()
  expect(toggle()).toHaveAttribute('aria-expanded', 'false')
  expect(boxes()).toHaveLength(0)
  key(root, '1')
  expect(await sent()).not.toHaveProperty('fivecs')
})

it('C opens it with the five questions, and 1 to 5 tick without deciding', async () => {
  const { root } = setup()
  key(root, 'c')
  expect(toggle()).toHaveAttribute('aria-expanded', 'true')
  expect(boxes().map((b) => b.getAttribute('aria-label') ?? b.closest('label')?.textContent)).toEqual([
    expect.stringContaining('Category: what type of paper is it?'),
    expect.stringContaining('Context:'),
    expect.stringContaining('Correctness:'),
    expect.stringContaining('Contributions:'),
    expect.stringContaining('Clarity:'),
  ])
  key(root, '1')
  key(root, '5')
  expect(ticks()).toEqual([true, false, false, false, true])
  expect(title()).toBe('Old one')
  expect(decide).not.toHaveBeenCalled()
  key(root, '1') // a second press takes the tick off
  expect(ticks()).toEqual([false, false, false, false, true])
})

it('sends the bitmask on the decision: Category and Correctness are 5', async () => {
  const { root } = setup()
  key(root, 'c')
  key(root, '1')
  key(root, '3')
  key(root, 'ArrowDown') // arrows still decide while it is open
  expect(title()).toBe('Middle')
  expect(await sent()).toMatchObject({ pile: 'skim', fivecs: 5 })
})

it('opened with nothing ticked sends 0, which is not the same as never opened', async () => {
  const { root } = setup()
  key(root, 'c')
  key(root, 'ArrowRight')
  expect((await sent()).fivecs).toBe(0)
  key(root, 'ArrowRight')
  expect(await sent(1)).not.toHaveProperty('fivecs')
})

it('ticks belong to the card: the next one starts collapsed and clear', async () => {
  const { root } = setup()
  key(root, 'c')
  key(root, '2')
  key(root, 'ArrowUp')
  expect(title()).toBe('Middle')
  expect(toggle()).toHaveAttribute('aria-expanded', 'false')
  expect(toggle()).not.toHaveTextContent('of 5')
  key(root, 'c')
  expect(ticks()).toEqual([false, false, false, false, false])
})

it('undo brings the card back with its ticks, and deciding again sends them', async () => {
  const { root } = setup()
  key(root, 'c')
  key(root, '2')
  key(root, '4')
  key(root, 'ArrowUp')
  await sent()
  key(root, 'u')
  expect(title()).toBe('Old one')
  expect(ticks()).toEqual([false, true, false, true, false])
  key(root, 'ArrowUp')
  expect((await sent(1)).fivecs).toBe(10)
})

it('a failed save returns the card with its ticks', async () => {
  decide.mockRejectedValueOnce(new Error('boom'))
  const { root } = setup()
  key(root, 'c')
  key(root, '1')
  key(root, 'ArrowRight')
  await screen.findByRole('alert')
  expect(title()).toBe('Old one')
  expect(ticks()).toEqual([true, false, false, false, false])
})

it('C closes it and the count stays on the line; digits are piles again', async () => {
  const { root } = setup()
  key(root, 'c')
  key(root, '1')
  key(root, '2')
  key(root, 'c')
  expect(boxes()).toHaveLength(0)
  expect(toggle()).toHaveTextContent('2 of 5')
  key(root, '2')
  expect(title()).toBe('Middle')
  expect(await sent()).toMatchObject({ pile: 'skim', fivecs: 3 })
})

it('Esc closes it before Esc leaves the desk, and a chip row before that', () => {
  const { root, onExit } = setup()
  key(root, 'c')
  key(root, 'Escape')
  expect(boxes()).toHaveLength(0)
  expect(onExit).not.toHaveBeenCalled()
  expect(root).toHaveFocus()
  key(root, 'Escape')
  expect(onExit).toHaveBeenCalledTimes(1)
})

it('a mouse tick leaves the keys working, and the toggle button returns focus to the desk', async () => {
  const { root } = setup()
  root.focus()
  fireEvent.click(toggle())
  expect(root).toHaveFocus()
  expect(fireEvent.mouseDown(screen.getByText(/^Context:/))).toBe(false) // the press does not take focus from the desk
  fireEvent.click(screen.getByRole('checkbox', { name: /Context:/ }))
  expect(ticks()).toEqual([false, true, false, false, false])
  key(root, 'ArrowRight')
  expect((await sent()).fivecs).toBe(2)
})

it('a press on a checklist line never starts a drag', async () => {
  const { root } = setup()
  key(root, 'c')
  const line = screen.getByText(/^Context:/)
  fireEvent.pointerDown(line, { clientX: 300, clientY: 100, pointerId: 1, button: 0 })
  fireEvent.pointerMove(line, { clientX: 500, clientY: 100, pointerId: 1 })
  fireEvent.pointerUp(line, { clientX: 500, clientY: 100, pointerId: 1 })
  expect(title()).toBe('Old one')
  expect(decide).not.toHaveBeenCalled()
})

it('Not relevant: while its chips show digits pick reasons, not ticks, and the ticks go with the commit', async () => {
  const { root } = setup()
  key(root, 'c')
  key(root, '3')
  key(root, '4') // ticks Contributions: the group is open
  key(root, 'ArrowLeft')
  expect(screen.getByRole('group', { name: 'Reason' })).toBeInTheDocument()
  key(root, 'c') // sleeps while the required chips are up
  expect(boxes()).toHaveLength(5)
  key(root, '1')
  expect(await sent()).toMatchObject({ pile: 'not_relevant', reason: 'off_topic', fivecs: 12 })
})

it('a skip records its ticks too, and Review the skipped starts clean', async () => {
  const { root } = setup()
  key(root, 'c')
  key(root, '1')
  key(root, ' ')
  expect(await sent()).toMatchObject({ pile: 'skip', fivecs: 1 })
  key(root, ' ')
  key(root, ' ')
  await sent(2)
  fireEvent.click(await screen.findByRole('button', { name: /Review the skipped/ }))
  await waitFor(() => expect(title()).toBe('Old one'))
  expect(boxes()).toHaveLength(0)
  expect(toggle()).not.toHaveTextContent('of 5')
})

it('says what opened and what was ticked in the live region', () => {
  const { root } = setup()
  key(root, 'c')
  expect(live()).toBe('Five Cs open. 1 to 5 tick, C closes.')
  key(root, '2')
  expect(live()).toBe('Context ticked.')
  key(root, '2')
  expect(live()).toBe('Context unticked.')
  key(root, 'c')
  expect(live()).toBe('Five Cs closed.')
})

it('C does nothing on the done screen', async () => {
  const { root } = setup()
  key(root, '1'); key(root, '1'); key(root, '1')
  await screen.findByText('That is the whole stack.')
  key(root, 'c')
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(live()).not.toContain('Five Cs')
})
