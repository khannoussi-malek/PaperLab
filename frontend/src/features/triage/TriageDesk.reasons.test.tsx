// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { api, ApiError, type Paper } from '@/api/client'
vi.mock('./pdfCache', () => ({ useCachedPdf: () => ({ doc: null, error: null }), retainOnly: vi.fn(), prefetchPdf: vi.fn() }))
vi.mock('../reader/PdfPage', () => ({ PdfPage: () => null }))
import { TriageDesk } from './TriageDesk'

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  Element.prototype.scrollIntoView = () => {}
  Element.prototype.hasPointerCapture = () => false
})
let decide: ReturnType<typeof vi.spyOn>
let patch: ReturnType<typeof vi.spyOn>
let undo: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  let n = 0
  decide = vi.spyOn(api, 'decideTriage').mockImplementation((async () => ({ event: { id: `e${++n}` } })) as never)
  patch = vi.spyOn(api, 'addTriageReason').mockResolvedValue({} as never)
  undo = vi.spyOn(api, 'undoTriage').mockResolvedValue({} as never)
  vi.spyOn(api, 'triageSummary').mockResolvedValue({ per_pile: {}, skipped: 0, card_ms: 0, pdf_opened: 0, decided: 0 } as never)
  vi.spyOn(api, 'paperSections').mockReturnValue(new Promise(() => {}) as never)
})
afterEach(() => { vi.useRealTimers(); cleanup(); sessionStorage.clear(); localStorage.clear(); vi.restoreAllMocks() })

const mk = (id: string, title: string) =>
  ({ id, title, authors: [], year: null, status: 'ready', has_pdf: true, reading_pass: null, triage: null, created_at: `2026-01-0${id}T00:00:00Z` }) as unknown as Paper
const base = [mk('1', 'Old one'), mk('2', 'Middle'), mk('3', 'New one')]

function setup() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TriageDesk papers={base} library={base} scope="library" sourceLabel="your library" filterKey="" onExit={vi.fn()} onShowKept={vi.fn()} />
    </QueryClientProvider>,
  )
  return screen.getByRole('group', { name: 'Triage' })
}
const key = (el: Element, k: string) => fireEvent.keyDown(el, { key: k })
const title = () => screen.getByRole('heading', { level: 2 }).textContent
const row = () => screen.queryByRole('group', { name: /^Why / })
const live = () => document.querySelector('[aria-live="polite"]')!.textContent
const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)) })

it('after Skim the card moves on at once and that pile\'s chips show as named buttons, keys 7 to 9', () => {
  const root = setup()
  expect(row()).toBeNull()
  key(root, '2')
  expect(title()).toBe('Middle')
  expect(row()).toHaveAccessibleName('Why Skim? Optional')
  expect(within(row()!).getAllByRole('button').map((b) => b.textContent)).toEqual(['7 background only', '8 related work', '9 partly relevant'])
})

it.each([['1', 'Read closely', '7 core to my question'], ['3', 'Later', '7 needs background first']])('key %s shows %s\'s chips', (k, pile, chip) => {
  const root = setup()
  key(root, k)
  expect(row()).toHaveAccessibleName(`Why ${pile}? Optional`)
  expect(screen.getByRole('button', { name: chip })).toBeInTheDocument()
})

it('8 adds the reason to the event just written and closes the row, keeping focus on the desk', async () => {
  const root = setup()
  root.focus()
  key(root, '2')
  key(root, '8')
  expect(row()).toBeNull()
  await waitFor(() => expect(patch).toHaveBeenCalledWith('e1', 'related_work'))
  expect(root).toHaveFocus()
  await waitFor(() => expect(live()).toBe('Reason added: related work.'))
  expect(decide).toHaveBeenCalledTimes(1)
})

it('a click on a chip does the same and focus returns to the desk', async () => {
  const root = setup()
  key(root, '1')
  const chip = screen.getByRole('button', { name: '9 key background' })
  chip.focus()
  fireEvent.click(chip)
  await waitFor(() => expect(patch).toHaveBeenCalledWith('e1', 'key_background'))
  expect(root).toHaveFocus()
})

it('a chip pressed before the decision has its event id waits for it', async () => {
  let release!: (v: unknown) => void
  decide.mockImplementationOnce((() => new Promise((r) => { release = r })) as never)
  const root = setup()
  key(root, '3')
  key(root, '7')
  await flush()
  expect(patch).not.toHaveBeenCalled()
  release({ event: { id: 'late' } })
  await waitFor(() => expect(patch).toHaveBeenCalledWith('late', 'needs_background'))
})

it('the row goes after 4 s with nothing written, and 7 to 9 then do nothing', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  const root = setup()
  key(root, '2')
  act(() => { vi.advanceTimersByTime(3900) })
  expect(row()).not.toBeNull()
  act(() => { vi.advanceTimersByTime(200) })
  expect(row()).toBeNull()
  key(root, '8')
  expect(title()).toBe('Middle')
  expect(patch).not.toHaveBeenCalled()
})

it('a pointer or focus on the row holds it; leaving gives it a fresh 4 s', () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  const root = setup()
  key(root, '2')
  fireEvent.pointerEnter(row()!)
  act(() => { vi.advanceTimersByTime(20_000) })
  expect(row()).not.toBeNull()
  fireEvent.pointerLeave(row()!)
  act(() => { vi.advanceTimersByTime(4100) })
  expect(row()).toBeNull()
})

it('the fast reader: 1 to 5 always decide the next paper, even with the row up, and write no reason', async () => {
  const root = setup()
  key(root, '2')
  key(root, '1')
  expect(title()).toBe('New one')
  expect(row()).toHaveAccessibleName('Why Read closely? Optional') // the row now belongs to the newer decision
  key(root, '3')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(3))
  expect((decide.mock.calls as unknown[][]).map((c) => (c[1] as { pile: string }).pile)).toEqual(['skim', 'read_closely', 'later'])
  await flush()
  expect(patch).not.toHaveBeenCalled()
})

it('a chip after a fast next decision goes on the newer event, never the older one', async () => {
  const root = setup()
  key(root, '2')
  key(root, '1')
  key(root, '7')
  await waitFor(() => expect(patch).toHaveBeenCalledWith('e2', 'core_to_my_question'))
  expect(patch).toHaveBeenCalledTimes(1)
})

it('Not relevant has its required chips and no optional row; 4 closes a row that was up', async () => {
  const root = setup()
  key(root, '2')
  key(root, '4')
  expect(row()).toBeNull()
  expect(screen.getByRole('group', { name: 'Reason' })).toBeInTheDocument()
  key(root, '1')
  expect(screen.queryByRole('group', { name: 'Reason' })).toBeNull()
  expect(row()).toBeNull()
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
  expect(decide.mock.calls[1][1]).toMatchObject({ pile: 'not_relevant', reason: 'off_topic' })
  expect(patch).not.toHaveBeenCalled()
})

it('Skip has no row and closes one that was up', () => {
  const root = setup()
  key(root, '2')
  key(root, ' ')
  expect(row()).toBeNull()
})

it('7 to 9 with no row are nothing', async () => {
  const root = setup()
  key(root, '7'); key(root, '8'); key(root, '9')
  await flush()
  expect(title()).toBe('Old one')
  expect(decide).not.toHaveBeenCalled()
  expect(patch).not.toHaveBeenCalled()
})

it('undo takes the row away with the decision it belonged to', async () => {
  const root = setup()
  key(root, '2')
  key(root, 'u')
  expect(row()).toBeNull()
  key(root, '8')
  await flush()
  expect(patch).not.toHaveBeenCalled()
})

it('a decision that fails takes its row away and no PATCH goes out', async () => {
  decide.mockRejectedValueOnce(new Error('boom'))
  const root = setup()
  key(root, '2')
  key(root, '8') // pressed before the failure is known
  await screen.findByRole('alert')
  expect(row()).toBeNull()
  expect(patch).not.toHaveBeenCalled()
})

it('a failed PATCH says so plainly and never blocks: the decision stands and the next one goes', async () => {
  patch.mockRejectedValueOnce(new Error('too late'))
  const root = setup()
  key(root, '2')
  key(root, '8')
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent("Couldn't add the reason: too late. The decision is saved.")
  expect(within(alert).queryByRole('button')).toBeNull()
  expect(live()).not.toContain('Reason added')
  expect(title()).toBe('Middle')
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1')
  key(root, '1')
  expect(title()).toBe('New one')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
  expect(screen.queryByRole('alert')).toBeNull()
})

it('the last card\'s row stays over the done screen and its keys still work', async () => {
  const root = setup()
  key(root, '1'); key(root, '1'); key(root, '2')
  await screen.findByText('That is the whole stack.')
  expect(row()).toHaveAccessibleName('Why Skim? Optional')
  key(root, '9')
  await waitFor(() => expect(patch).toHaveBeenCalledWith('e3', 'partly_relevant'))
})

it('with the five Cs open on the next card, 1 ticks and 7 is still the chip', async () => {
  const root = setup()
  key(root, '2')
  key(root, 'c')
  key(root, '1')
  expect(screen.getAllByRole('checkbox')[0]).toHaveAttribute('aria-checked', 'true')
  key(root, '7')
  await waitFor(() => expect(patch).toHaveBeenCalledWith('e1', 'background_only'))
})

it('announces the offer with the decision, once', () => {
  const root = setup()
  key(root, '2')
  expect(live()).toBe('Old one. Skim. 1 of 3 done. Reason optional: 7, 8 or 9. Middle. Paper 2 of 3. Undecided. Abstract below.')
})

it('at phone width the chips are tall enough to press', () => {
  window.innerWidth = 500
  const root = setup()
  key(root, '2')
  expect(screen.getByRole('button', { name: '7 background only' })).toHaveClass('min-h-11')
  window.innerWidth = 1024
})

const REASON_WAITS = "The reason you picked wasn't saved; Retry sends it too."

it('says Reason added only once the PATCH has succeeded', async () => {
  let release!: (v: unknown) => void
  patch.mockImplementationOnce((() => new Promise((r) => { release = r })) as never)
  const root = setup()
  key(root, '2')
  key(root, '8')
  await waitFor(() => expect(patch).toHaveBeenCalled())
  await flush()
  expect(live()).not.toContain('Reason added')
  release({})
  await waitFor(() => expect(live()).toBe('Reason added: related work.'))
})

it('a chip on a decision whose POST fails says the reason was not saved, and Retry sends it after the decision', async () => {
  decide.mockRejectedValueOnce(new Error('boom'))
  const root = setup()
  key(root, '2')
  key(root, '8')
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(`Couldn't save: boom ${REASON_WAITS}`))
  expect(live()).not.toContain('Reason added')
  expect(patch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await waitFor(() => expect(patch).toHaveBeenCalledWith('e1', 'related_work'))
  expect(patch).toHaveBeenCalledTimes(1)
  await waitFor(() => expect(live()).toBe('Reason added: related work.'))
})

it('a Retry that fails again still says the reason was not saved, and one that then works sends it once', async () => {
  decide.mockRejectedValueOnce(new Error('boom')).mockRejectedValueOnce(new Error('again'))
  const root = setup()
  key(root, '2')
  key(root, '8')
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(REASON_WAITS))
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(`Couldn't save: again ${REASON_WAITS}`))
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  await waitFor(() => expect(patch).toHaveBeenCalledTimes(1))
})

it('a fresh decision on the returned card does not inherit the reason', async () => {
  decide.mockRejectedValueOnce(new Error('boom'))
  const root = setup()
  key(root, '2')
  key(root, '8')
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(REASON_WAITS))
  key(root, '1')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
  await flush()
  expect(patch).not.toHaveBeenCalled()
})

it('a chip on a decision already undone stays quiet when its POST fails', async () => {
  decide.mockRejectedValueOnce(new Error('boom'))
  const root = setup()
  key(root, '2')
  key(root, '8')
  key(root, 'u')
  await waitFor(() => expect(decide).toHaveBeenCalled())
  await flush()
  expect(screen.queryByRole('alert')).toBeNull()
  expect(patch).not.toHaveBeenCalled()
})

it('a failed decision keeps its row closed after Retry: no stale row with a fresh timer', async () => {
  decide.mockRejectedValueOnce(new Error('boom'))
  const root = setup()
  key(root, '2')
  await screen.findByRole('alert')
  expect(row()).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(title()).toBe('Middle')
  expect(row()).toBeNull()
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
  await flush()
  expect(row()).toBeNull()
})

it('an older decision failing leaves the newer decision\'s row alone', async () => {
  decide.mockRejectedValueOnce(new Error('boom'))
  const root = setup()
  key(root, '2')
  key(root, '1')
  await screen.findByRole('alert')
  expect(row()).toHaveAccessibleName('Why Read closely? Optional')
})

it('an undo that fails puts the decision back without its row', async () => {
  undo.mockRejectedValueOnce(new Error('boom'))
  const root = setup()
  key(root, '2')
  await waitFor(() => expect(decide).toHaveBeenCalled())
  await flush()
  key(root, 'u')
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent("Couldn't undo: boom"))
  expect(title()).toBe('Middle')
  expect(row()).toBeNull()
})

it('an undo refused as changed elsewhere brings no row back either', async () => {
  undo.mockRejectedValueOnce(new ApiError('changed', 409, { detail: 'changed_since' }))
  const root = setup()
  key(root, '2')
  await waitFor(() => expect(decide).toHaveBeenCalled())
  await flush()
  key(root, 'u')
  await screen.findByRole('alert')
  expect(row()).toBeNull()
})

const chipOf = () => screen.getByRole('button', { name: '7 background only' })

it('focus on a chip holds the row; losing it gives a fresh 4 s', () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  const root = setup()
  key(root, '2')
  act(() => { chipOf().focus() })
  act(() => { vi.advanceTimersByTime(20_000) })
  expect(row()).not.toBeNull()
  act(() => { chipOf().blur() })
  act(() => { vi.advanceTimersByTime(3900) })
  expect(row()).not.toBeNull()
  act(() => { vi.advanceTimersByTime(200) })
  expect(row()).toBeNull()
})

it('the pointer leaving does not restart the timer under a focused chip, nor blur under a hovering pointer', () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  const root = setup()
  key(root, '2')
  act(() => { chipOf().focus() })
  fireEvent.pointerEnter(row()!)
  fireEvent.pointerLeave(row()!)
  act(() => { vi.advanceTimersByTime(20_000) })
  expect(row()).not.toBeNull()
  fireEvent.pointerEnter(row()!)
  act(() => { chipOf().blur() })
  act(() => { vi.advanceTimersByTime(20_000) })
  expect(row()).not.toBeNull()
  fireEvent.pointerLeave(row()!)
  act(() => { vi.advanceTimersByTime(4100) })
  expect(row()).toBeNull()
})
