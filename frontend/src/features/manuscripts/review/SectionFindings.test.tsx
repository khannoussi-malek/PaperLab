// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { SectionFinding, SectionReview } from '@/api/client'
import { ReviewPanel } from './ReviewPanel'
import { SectionFindings } from './SectionFindings'

const S = (n: number, preview: string) => ({ kind: 'sentence' as const, n, hash: `h${n}`, preview })
const N = (n: number, label: string | null, id: string | null = 'n1') => ({ kind: 'note' as const, n, note_id: id, paper_id: id && 'p1', label })
const findings: SectionFinding[] = [
  { kind: 'missing', point: 'No sample size is named', refs: [] },
  { kind: 'unsupported', point: 'The memory claim has no figure behind it', refs: [S(2, 'Sleep improves memory in adults.')] },
  { kind: 'supported', point: 'The aim is clear', refs: [S(1, 'Sleep is vital for health'), N(1, 'Smith 2021 p.4'), N(2, null, null)] },
]
const review = (o: Partial<SectionReview> = {}): SectionReview => ({ id: 'r1', file: 'main.tex', section_hash: 'h', title: 'Our approach', role: 'method', role_source: 'guessed', status: 'done', reason: null, findings, dropped: 0, model: 'm', ai: true, created_at: '2026-10-31T00:00:00Z', ...o })
function show(r: SectionReview, o: Record<string, unknown> = {}) {
  const props = { review: r, stale: false, hasWorkspace: true, onJump: vi.fn(), onCancel: vi.fn(), onReviewAgain: vi.fn(), ...o }
  render(<SectionFindings {...props} />)
  return props
}
beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

test('done: heading, role, AI badge and the three groups with icon and word', () => {
  show(review())
  expect(screen.getByRole('heading', { name: '“Our approach”' })).toBeInTheDocument()
  expect(screen.getByText('Reviewed as: Method')).toBeInTheDocument()
  expect(screen.getByText('AI')).toBeInTheDocument()
  for (const [title, point] of [['Missing', 'No sample size is named'], ['Unsupported', 'The memory claim has no figure behind it'], ['Supported', 'The aim is clear']]) {
    const group = screen.getByRole('group', { name: title })
    expect(group.querySelector('svg')).not.toBeNull() // never colour alone: an icon and the word
    expect(within(group).getByText(point)).toBeInTheDocument()
  }
})

test('a chosen role says so', () => {
  show(review({ role: 'results', role_source: 'chosen' }))
  expect(screen.getByText('Reviewed as: Results (you chose this)')).toBeInTheDocument()
})

test('a sentence chip moves the selection; a note chip opens the note in a new tab; a removed note is no link', () => {
  const open = vi.spyOn(window, 'open').mockReturnValue(null)
  const { onJump } = show(review())
  fireEvent.click(screen.getByRole('button', { name: 'S2 · Sleep improves memory in adults.' }))
  expect(onJump).toHaveBeenCalledWith('h2')
  fireEvent.click(screen.getByRole('button', { name: /Note · Smith 2021 p\.4/ }))
  expect(open).toHaveBeenCalledWith('#/papers/p1?note=n1', '_blank', 'noopener')
  expect(screen.getByText('Note · note removed')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /note removed/ })).toBeNull()
})

test('queued and running say Reviewing… with Cancel', () => {
  for (const status of ['queued', 'running'] as const) {
    const { onCancel } = show(review({ status, findings: [] }))
    expect(screen.getByText('Reviewing…')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledWith('r1')
    document.body.innerHTML = ''
  }
})

test('a live review whose poll was lost says so, with Review again instead of Reviewing…', () => {
  const r = review({ status: 'running', findings: [] })
  const { onReviewAgain } = show(r, { lost: true })
  expect(screen.queryByText('Reviewing…')).toBeNull()
  expect(screen.getByText("Couldn't check on this review. Try Review again.")).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Review again' }))
  expect(onReviewAgain).toHaveBeenCalledWith(r)
  document.body.innerHTML = ''
  show(review(), { lost: true }) // a finished review is unaffected
  expect(screen.queryByText("Couldn't check on this review. Try Review again.")).toBeNull()
})

test('the panel passes a lost poll to the card and its announcer', () => {
  const base = { run: null, items: [], dismissed: [], startError: null, cancel: vi.fn(), dismiss: vi.fn(), restore: vi.fn() } as never
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ReviewPanel manuscriptId="m" review={base} stale={[]} onJump={() => {}} onCite={async () => null} onCheckAgain={() => {}}
        sections={{ reviews: [review({ status: 'running', findings: [] })], stale: [], hasWorkspace: true, lost: true, onCancel: vi.fn(), onReviewAgain: vi.fn() }} />
    </QueryClientProvider>,
  )
  expect(screen.getByRole('article')).toHaveTextContent("Couldn't check on this review. Try Review again.")
  expect(screen.getByRole('status', { name: 'Section review status' })).toHaveTextContent("Couldn't check on “Our approach”. Try Review again.")
})

test('failed, cancelled and interrupted reviews say why in plain words', () => {
  show(review({ status: 'failed', reason: 'model_error', findings: [] }))
  expect(screen.getByText("The model didn't give a usable answer")).toBeInTheDocument()
  document.body.innerHTML = ''
  show(review({ status: 'failed', reason: 'cancelled', findings: [] }))
  expect(screen.getByText('Cancelled')).toBeInTheDocument()
  document.body.innerHTML = ''
  show(review({ status: 'interrupted', findings: [] }))
  expect(screen.getByText('The review was interrupted. Run it again.')).toBeInTheDocument()
})

test('dropped lines are counted', () => {
  show(review({ dropped: 2 }))
  expect(screen.getByText("2 lines weren't in a usable form.")).toBeInTheDocument()
  document.body.innerHTML = ''
  show(review({ dropped: 1 }))
  expect(screen.getByText("1 line wasn't in a usable form.")).toBeInTheDocument()
})

test('without a workspace it says the notes were not used', () => {
  show(review(), { hasWorkspace: false })
  expect(screen.getByText("Your notes weren't used — pick a workspace to include them.")).toBeInTheDocument()
})

test('a stale review is greyed with Review again, off while a review is live', () => {
  const r = review()
  const { onReviewAgain } = show(r, { stale: true })
  fireEvent.click(screen.getByRole('button', { name: 'Review again' }))
  expect(onReviewAgain).toHaveBeenCalledWith(r)
  document.body.innerHTML = ''
  show(r, { stale: true, busy: true })
  expect(screen.getByRole('button', { name: 'Review again' })).toBeDisabled()
})

test('one polite status region, there before any review, announces start and finish', () => {
  const base = { run: null, items: [], dismissed: [], startError: null, cancel: vi.fn(), dismiss: vi.fn(), restore: vi.fn() } as never
  const panel = (reviews: SectionReview[]) => (
    <QueryClientProvider client={new QueryClient()}>
      <ReviewPanel manuscriptId="m" review={base} stale={[]} onJump={() => {}} onCite={async () => null} onCheckAgain={() => {}}
        sections={{ reviews, stale: [], hasWorkspace: true, onCancel: vi.fn(), onReviewAgain: vi.fn() }} />
    </QueryClientProvider>
  )
  const { rerender } = render(panel([]))
  const region = screen.getByRole('status', { name: 'Section review status' })
  expect(region).toHaveAttribute('aria-live', 'polite')
  expect(region).toHaveTextContent(/^$/)
  rerender(panel([review({ status: 'running', findings: [] })]))
  expect(screen.getByRole('status', { name: 'Section review status' })).toBe(region)
  expect(region).toHaveTextContent('Reviewing “Our approach”…')
  rerender(panel([review()]))
  expect(screen.getByRole('status', { name: 'Section review status' })).toBe(region)
  expect(region).toHaveTextContent('Review of “Our approach” done: 1 missing, 1 unsupported, 1 supported.')
})

test('D118: nothing in a finding can be copied or inserted', () => {
  const write = vi.fn()
  Object.assign(navigator, { clipboard: { writeText: write } })
  vi.spyOn(window, 'open').mockReturnValue(null)
  show(review())
  const names = screen.getAllByRole('button').map((b) => b.textContent ?? '')
  expect(names.length).toBeGreaterThan(0)
  expect(names.every((n) => /^(S\d|Note) · /.test(n))).toBe(true) // only the chips, which move the selection or open a note
  expect(screen.queryByRole('button', { name: /copy|insert|apply|use|replace|cite/i })).toBeNull()
  expect(screen.queryByRole('link')).toBeNull()
  for (const b of screen.getAllByRole('button')) fireEvent.click(b)
  expect(write).not.toHaveBeenCalled()
})

test('the panel shows a Section review group above the citations, even with no citation check', () => {
  const base = { run: null, items: [], dismissed: [], startError: null, cancel: vi.fn(), dismiss: vi.fn(), restore: vi.fn() } as never
  const sections = { reviews: [review(), review({ id: 'r2', title: 'Old part', section_hash: 'gone' })], stale: [review({ id: 'r2', title: 'Old part', section_hash: 'gone' })], hasWorkspace: true, onCancel: vi.fn(), onReviewAgain: vi.fn() }
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ReviewPanel manuscriptId="m" review={base} stale={[]} onJump={() => {}} onCite={async () => null} onCheckAgain={() => {}} sections={sections} />
    </QueryClientProvider>,
  )
  expect(screen.getByText('Section review')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '“Our approach”' })).toBeInTheDocument()
  const changed = screen.getByText('Changed since reviewed').closest('div')!
  expect(within(changed).getByText('“Old part”')).toBeInTheDocument()
  expect(within(changed).getByRole('button', { name: 'Review again' })).toBeInTheDocument()
})
