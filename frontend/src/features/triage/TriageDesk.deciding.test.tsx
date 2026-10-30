// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'
import { TriageDesk } from './TriageDesk'

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  Element.prototype.scrollIntoView = () => {}
  Element.prototype.hasPointerCapture = () => false
})
let decide: ReturnType<typeof vi.spyOn>
let undo: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  let n = 0
  decide = vi.spyOn(api, 'decideTriage').mockImplementation((async () => ({ event: { id: `e${++n}` } })) as never)
  undo = vi.spyOn(api, 'undoTriage').mockResolvedValue({} as never)
  vi.spyOn(api, 'triageSummary').mockResolvedValue({ per_pile: { read_closely: 1, skim: 1 }, skipped: 1, card_ms: 60_000, pdf_opened: 0, decided: 2 } as never)
  vi.spyOn(api, 'paperSections').mockReturnValue(new Promise(() => {}) as never) // nothing ever loads
})
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear(); vi.restoreAllMocks() })

const mk = (id: string, title: string) =>
  ({ id, title, authors: [], year: null, status: 'ready', has_pdf: true, reading_pass: null, triage: null, created_at: `2026-01-0${id}T00:00:00Z` }) as unknown as Paper
const base = [mk('1', 'Old one'), mk('2', 'Middle'), mk('3', 'New one')]

function setup(onExit = vi.fn(), onShowKept = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TriageDesk papers={base} library={base} scope="library" sourceLabel="your library" filterKey="" onExit={onExit} onShowKept={onShowKept} />
    </QueryClientProvider>,
  )
  return { onExit, onShowKept, root: screen.getByRole('group', { name: 'Triage' }) }
}
const key = (el: Element, k: string, init: KeyboardEventInit = {}) => fireEvent.keyDown(el, { key: k, ...init })
const title = () => screen.getByRole('heading', { level: 2 }).textContent
const decided = () => screen.getByRole('progressbar').getAttribute('aria-valuenow')
const live = () => document.querySelector('[aria-live="polite"]')!.textContent

it('1, 2 and 3 commit at once with pdf_opened false and no loading needed', async () => {
  const { root } = setup()
  key(root, '1')
  expect(title()).toBe('Middle')
  key(root, '2')
  key(root, '3')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(3))
  expect((decide.mock.calls as unknown[][]).map((c) => [c[0], (c[1] as { pile: string; pdf_opened: boolean }).pile, (c[1] as { pdf_opened: boolean }).pdf_opened]))
    .toEqual([['1', 'read_closely', false], ['2', 'skim', false], ['3', 'later', false]])
})

it('says each outcome in its exact words and the progress follows', () => {
  const { root } = setup()
  expect(decided()).toBe('0')
  key(root, '1')
  expect(live()).toBe('Old one. Read closely. 1 of 3 done. Middle. Paper 2 of 3. Undecided. Abstract below.')
  expect(decided()).toBe('1')
  key(root, 'u')
  expect(live()).toBe('Old one. Decision undone. Undecided.')
  expect(decided()).toBe('0')
})

it('focus is on the desk root after a button press and after a decision', () => {
  const { root } = setup()
  const controls = screen.getByRole('group', { name: 'Decide' })
  const skim = within(controls).getByRole('button', { name: /Skim/ })
  skim.focus()
  fireEvent.click(skim)
  expect(root).toHaveFocus()
  expect(title()).toBe('Middle')
  key(root, '3')
  expect(root).toHaveFocus()
})

it('4 shows the reason chips and sends nothing until a chip commits', async () => {
  const { root } = setup()
  key(root, '4')
  expect(screen.getByRole('group', { name: 'Reason' })).toBeInTheDocument()
  expect(live()).toBe('Pick a reason, 1 to 6')
  expect(title()).toBe('Old one')
  expect(decide).not.toHaveBeenCalled()
  key(root, '1')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(1))
  expect(decide.mock.calls[0][1]).toMatchObject({ pile: 'not_relevant', reason: 'off_topic', pdf_opened: false })
  expect(screen.queryByRole('group', { name: 'Reason' })).toBeNull()
  expect(title()).toBe('Middle')
})

it('Left arrow, the button and the target all open the chips, not a decision', () => {
  const { root } = setup()
  key(root, 'ArrowLeft')
  expect(screen.getByRole('group', { name: 'Reason' })).toBeInTheDocument()
  key(root, 'Escape')
  fireEvent.click(within(screen.getByRole('group', { name: 'Decide' })).getByRole('button', { name: /Not relevant/ }))
  expect(screen.getByRole('group', { name: 'Reason' })).toBeInTheDocument()
  key(root, 'Escape')
  fireEvent.click(document.querySelector('[data-triage-target="not_relevant"]')!)
  expect(screen.getByRole('group', { name: 'Reason' })).toBeInTheDocument()
  expect(decide).not.toHaveBeenCalled()
})

it('a drag onto Not relevant opens the chips and the card waits over the target', () => {
  setup()
  const h = screen.getByRole('heading', { level: 2 })
  fireEvent.pointerDown(h, { clientX: 300, clientY: 100, pointerId: 1, button: 0 })
  fireEvent.pointerMove(h, { clientX: 100, clientY: 100, pointerId: 1 })
  fireEvent.pointerUp(h, { clientX: 100, clientY: 100, pointerId: 1 })
  expect(screen.getByRole('group', { name: 'Reason' })).toBeInTheDocument()
  expect(document.querySelector('[data-triage-target="not_relevant"]')).toHaveAttribute('data-active')
  expect(decide).not.toHaveBeenCalled()
})

it('Esc cancels the chips back to undecided, sends nothing and does not exit', () => {
  const { root, onExit } = setup()
  key(root, '4')
  key(root, 'Escape')
  expect(screen.queryByRole('group', { name: 'Reason' })).toBeNull()
  expect(title()).toBe('Old one')
  expect(decide).not.toHaveBeenCalled()
  expect(onExit).not.toHaveBeenCalled()
  key(root, 'Escape')
  expect(onExit).toHaveBeenCalledTimes(1)
})

it('other + Enter commits with the note, and digits are piles again afterwards', async () => {
  const { root } = setup()
  key(root, '4')
  key(root, '6')
  const note = screen.getByRole('textbox', { name: 'Note' })
  fireEvent.change(note, { target: { value: 'not mine' } })
  key(note, 'Enter')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(1))
  expect(decide.mock.calls[0][1]).toMatchObject({ reason: 'other', note: 'not mine' })
  expect(root).toHaveFocus()
  key(root, '2')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
  expect(decide.mock.calls[1][1]).toMatchObject({ pile: 'skim' })
})

it('Mod+Z undoes outside text fields but not inside the note', async () => {
  const { root } = setup()
  key(root, '1')
  await waitFor(() => expect(decide).toHaveBeenCalled())
  key(root, '4')
  key(root, '6')
  key(screen.getByRole('textbox', { name: 'Note' }), 'z', { metaKey: true })
  expect(undo).not.toHaveBeenCalled()
  key(screen.getByRole('textbox', { name: 'Note' }), 'Escape')
  await waitFor(() => expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '1'))
  key(root, 'z', { metaKey: true })
  await waitFor(() => expect(undo).toHaveBeenCalledWith('e1'))
  expect(title()).toBe('Old one')
})

it('a failed save returns the card with the alert, does not advance, and Retry decides again', async () => {
  decide.mockRejectedValueOnce(new Error('boom'))
  const { root } = setup()
  key(root, '1')
  expect(decided()).toBe('1')
  await screen.findByRole('alert')
  expect(screen.getByRole('alert')).toHaveTextContent("Couldn't save: boom")
  expect(title()).toBe('Old one')
  expect(decided()).toBe('0')
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(title()).toBe('Middle')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(2))
})

it('Esc closes the help before leaving, and the help lists only keys that exist', () => {
  const { root, onExit } = setup()
  key(root, '?', { shiftKey: true })
  const help = screen.getByRole('dialog')
  const text = help.textContent ?? ''
  for (const k of ['Read closely', 'Skim', 'Later', 'Not relevant', 'Skip', 'Undo', 'PDF', 'abstract', 'F6', 'Esc']) expect(text).toContain(k)
  expect(text).not.toMatch(/\bS\b|Tab to|Delete/)
  key(help, 'Escape')
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(onExit).not.toHaveBeenCalled()
  key(root, 'Escape')
  expect(onExit).toHaveBeenCalledTimes(1)
})

it('Esc during a drag cancels the drag and does not leave the desk', () => {
  const { onExit } = setup()
  const h = screen.getByRole('heading', { level: 2 })
  fireEvent.pointerDown(h, { clientX: 300, clientY: 100, pointerId: 1, button: 0 })
  fireEvent.pointerMove(h, { clientX: 100, clientY: 100, pointerId: 1 })
  key(h, 'Escape')
  expect(onExit).not.toHaveBeenCalled()
})

it('the done screen reports the session, Undo brings the last card back and Review the skipped restarts with them', async () => {
  const { root, onShowKept, onExit } = setup()
  key(root, '1')
  key(root, ' ')
  key(root, '2')
  expect(await screen.findByText('That is the whole stack.')).toBeInTheDocument()
  expect(await screen.findByText('PDF opened for 0 of 2')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Show kept papers in the list' }))
  expect(onShowKept).toHaveBeenCalled()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Review the skipped (1)' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Review the skipped (1)' }))
  expect(title()).toBe('Middle')
  expect(screen.getByText(/Triage · your library · 1 left of 3/)).toBeInTheDocument()
  key(root, '1')
  fireEvent.click(await screen.findByRole('button', { name: /Undo: Read closely/ }))
  expect(title()).toBe('Middle')
  expect(onExit).not.toHaveBeenCalled()
})

const clickReal = (el: HTMLElement) => { el.focus(); fireEvent.click(el) }
const finish = async (root: Element) => {
  key(root, '1'); key(root, ' '); key(root, '2')
  await screen.findByText('That is the whole stack.')
}

it('Start over from the done screen opens a new session and a fresh stack without resending decisions', async () => {
  const { root } = setup()
  const first = sessionStorage.getItem('paperlab-triage-session:library')
  await finish(root)
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(3))
  clickReal(screen.getByRole('button', { name: 'Start over' }))
  const second = sessionStorage.getItem('paperlab-triage-session:library')
  expect(second).not.toBeNull()
  expect(second).not.toBe(first)
  expect(decided()).toBe('0')
  expect(screen.getByText(/Triage · your library · 3 left of 3/)).toBeInTheDocument()
  expect(title()).toBe('Old one')
  expect(decide).toHaveBeenCalledTimes(3)
  key(document.activeElement!, '1')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(4))
  expect((decide.mock.calls[3][1] as { session_id: string }).session_id).toBe(second)
})

it('the bar offers Start over while cards are left', async () => {
  setup()
  key(screen.getByRole('group', { name: 'Triage' }), '1')
  await waitFor(() => expect(screen.getByRole('button', { name: 'Start over' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Start over' }))
  expect(decided()).toBe('0')
})

it('after Review the skipped, Show kept and Start over a key sent to the active element is handled', async () => {
  const { root } = setup()
  await finish(root)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Review the skipped (1)' })).toBeEnabled())
  clickReal(screen.getByRole('button', { name: 'Review the skipped (1)' }))
  expect(document.activeElement).toBe(root)
  key(document.activeElement!, '3')
  await waitFor(() => expect(decide).toHaveBeenCalledTimes(4))
  clickReal(await screen.findByRole('button', { name: 'Show kept papers in the list' }))
  expect(document.activeElement).toBe(root)
  clickReal(screen.getByRole('button', { name: 'Start over' }))
  expect(document.activeElement).toBe(root)
  key(document.activeElement!, '2')
  expect(title()).toBe('Middle')
})

it('a held pile key shows its stamp and lights nothing else; keyup and blur clear it', () => {
  const { root } = setup()
  expect(document.querySelector('[data-triage-stamp]')).toBeNull()
  key(root, '4')
  expect(document.querySelector('[data-triage-stamp]')).toHaveTextContent('Not relevant')
  fireEvent.keyUp(root, { key: '4' })
  // chips are showing: the stamp and the target stay
  expect(document.querySelector('[data-triage-stamp]')).toHaveTextContent('Not relevant')
  key(root, 'Escape')
  expect(document.querySelector('[data-triage-stamp]')).toBeNull()
  // a key that commits leaves no stamp on the next card
  key(root, 'ArrowRight')
  expect(title()).toBe('Middle')
  expect(document.querySelector('[data-triage-stamp]')).toBeNull()
  key(root, '2')
  expect(document.querySelector('[data-triage-stamp]')).toBeNull()
  fireEvent.blur(window)
  expect(document.querySelector('[data-triage-stamp]')).toBeNull()
})

it('Start over waits for pending saves: disabled with a reason, enabled once they land', async () => {
  let release!: (v: unknown) => void
  decide.mockImplementationOnce((() => new Promise((r) => { release = r })) as never)
  const { root } = setup()
  key(root, '1')
  const bar = screen.getByRole('button', { name: 'Start over' })
  expect(bar).toBeDisabled()
  expect(bar).toHaveAttribute('title', 'Saving… try again in a moment')
  key(root, ' '); key(root, '2')
  await screen.findByText('That is the whole stack.')
  expect(screen.getByRole('button', { name: 'Start over' })).toBeDisabled()
  release({ event: { id: 'late' } })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Start over' })).toBeEnabled())
})
