// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, type CheckItem } from '@/api/client'
import { ReviewPanel } from './ReviewPanel'

const item = (o: Partial<CheckItem>): CheckItem => ({ id: 'i1', kind: 'cited', file: 'main.tex', sentence_hash: 'h1', sentence: 'Models help a lot.', ord: 0, cite_key: 'lewis2020', paper_id: 'p1', paper_title: 'Lewis', status: 'done', verdict: 'supported', reason: 'It says so.', quote: 'models help', page: 4, chunk_id: 'c1', output_id: null, model: 'm', ai: true, ...o })
const base = { run: { id: 'r', status: 'done', total: 1, done: 1, reason: null, uncited_skipped: 0 }, items: [] as CheckItem[], dismissed: [] as string[], startError: null as string | null, cancel: vi.fn(), dismiss: vi.fn(async () => {}), restore: vi.fn(async () => {}) }
function show(over: Record<string, unknown> = {}, props: Record<string, unknown> = {}) {
  const review = { ...base, ...over } as never
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ReviewPanel manuscriptId="m" review={review} stale={[]} onJump={() => {}} onCite={async () => null} onCheckAgain={() => {}} {...props} />
    </QueryClientProvider>,
  )
}
beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

test('citations: verdict text, AI badge, key, sentence and a page link that opens the passage', async () => {
  const open = vi.spyOn(window, 'open').mockReturnValue(null)
  show({ items: [item({})] })
  expect(screen.getByText('Citations')).toBeInTheDocument()
  expect(screen.getByText('Supports')).toBeInTheDocument()
  expect(screen.getByText('AI')).toBeInTheDocument()
  expect(screen.getByText('lewis2020')).toBeInTheDocument()
  await fireEvent.click(screen.getByRole('link', { name: 'Page 4' }))
  expect(open).toHaveBeenCalledWith('#/papers/p1?chunk=c1&page=4', '_blank', 'noopener')
})

test('a row click jumps to the sentence', async () => {
  const onJump = vi.fn()
  show({ items: [item({})] }, { onJump })
  await fireEvent.click(screen.getByRole('button', { name: /Models help a lot/ }))
  expect(onJump).toHaveBeenCalledWith('h1')
})

test('failed rows say why in plain words', () => {
  show({ items: [item({ status: 'failed', verdict: null, reason: 'check_failed' }), item({ id: 'i2', sentence_hash: 'h2', verdict: 'cannot_verify', reason: 'key_not_found' })] })
  expect(screen.getByText("The model didn't give a usable answer")).toBeInTheDocument()
  expect(screen.getByText('This key matches no paper in the library')).toBeInTheDocument()
})

test('states: running with progress, cancelled, failed, empty, skipped, no model', async () => {
  const cancel = vi.fn()
  const { unmount } = show({ run: { ...base.run, status: 'running', total: 19, done: 7 }, cancel })
  expect(screen.getByText('Checking 7 of 19…')).toBeInTheDocument()
  await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(cancel).toHaveBeenCalled()
  unmount()
  show({ run: { ...base.run, status: 'cancelled' } })
  expect(screen.getByText(/cancelled/i)).toBeInTheDocument()
})

test('failed run, empty run, skipped sentences and no model', () => {
  const a = show({ run: { ...base.run, status: 'failed', reason: 'no_model' } })
  expect(screen.getByText('Add a model in Settings to run the reviewer.')).toBeInTheDocument()
  a.unmount()
  const b = show({ items: [] })
  expect(screen.getByText('Nothing to check — no sentences cite a paper.')).toBeInTheDocument()
  b.unmount()
  show({ items: [item({})], run: { ...base.run, uncited_skipped: 3 } })
  expect(screen.getByText("3 more sentences weren't checked. Select them to check.")).toBeInTheDocument()
})

const claim = item({ id: 'c1', kind: 'uncited', sentence_hash: 'h9', sentence: 'Everyone agrees.', verdict: 'claim', cite_key: null, paper_id: null, quote: null, page: null, chunk_id: null, reason: null })

test('Find papers lists proposals and Cite this hands the paper to onCite', async () => {
  const P = (n: string) => ({ paper_id: n, key: `k${n}`, passages: [{ chunk_id: `c${n}`, page: 1, text: `text ${n}` }] })
  vi.spyOn(api, 'findEvidence').mockResolvedValue({ sentence_hash: 'h9', verdicts: 'unavailable', papers: [P('1'), P('2'), P('3')] })
  const onCite = vi.fn(async () => null)
  show({ items: [claim] }, { onCite })
  expect(screen.getByText('Claims with no citation')).toBeInTheDocument()
  expect(screen.getByText('Needs a citation')).toBeInTheDocument()
  await fireEvent.click(screen.getByRole('button', { name: 'Find papers' }))
  const buttons = await screen.findAllByRole('button', { name: 'Cite this' })
  expect(buttons).toHaveLength(3)
  await fireEvent.click(buttons[1])
  expect(onCite).toHaveBeenCalledWith('h9', '2')
})

test('a cite problem is shown', async () => {
  vi.spyOn(api, 'findEvidence').mockResolvedValue({ sentence_hash: 'h9', verdicts: 'unavailable', papers: [{ paper_id: '1', key: 'k1', passages: [{ chunk_id: 'c', page: 1, text: 't' }] }] })
  show({ items: [claim] }, { onCite: async () => 'That sentence changed. Check again.' })
  await fireEvent.click(screen.getByRole('button', { name: 'Find papers' }))
  await fireEvent.click(await screen.findByRole('button', { name: 'Cite this' }))
  expect(await screen.findByText('That sentence changed. Check again.')).toBeInTheDocument()
})

test('Not a claim dismisses; a dismissed claim can be restored', async () => {
  const dismiss = vi.fn(async () => {})
  const a = show({ items: [claim], dismiss })
  await fireEvent.click(screen.getByRole('button', { name: 'Not a claim' }))
  expect(dismiss).toHaveBeenCalledWith('h9')
  a.unmount()
  const restore = vi.fn(async () => {})
  show({ items: [claim], dismissed: ['h9'], restore })
  expect(screen.getByText(/Dismissed/)).toBeInTheDocument()
  await fireEvent.click(screen.getByRole('button', { name: 'Restore' }))
  expect(restore).toHaveBeenCalledWith('h9')
})

test('changed items are greyed with Check again', async () => {
  const onCheckAgain = vi.fn()
  show({ items: [] }, { stale: [item({})], onCheckAgain })
  expect(screen.getByText('Changed since checked')).toBeInTheDocument()
  await fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
  expect(onCheckAgain).toHaveBeenCalled()
})

test('collapses and remembers it', async () => {
  const a = show({ items: [item({})] })
  await fireEvent.click(screen.getByRole('button', { name: /Citation check/ }))
  expect(screen.queryByText('Citations')).toBeNull()
  a.unmount()
  show({ items: [item({})] })
  await waitFor(() => expect(screen.queryByText('Citations')).toBeNull())
})

test('an uncited row that failed or could not be verified is not offered as a claim', () => {
  show({ items: [
    { ...claim, id: 'f1', status: 'failed', verdict: null, reason: 'cancelled', sentence_hash: 'f1' },
    { ...claim, id: 'f2', verdict: 'cannot_verify', reason: 'model_error', sentence_hash: 'f2' },
  ] })
  expect(screen.queryByText('Needs a citation')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Find papers' })).toBeNull()
  expect(screen.getAllByText("Couldn't check")).toHaveLength(2)
  expect(screen.getByText('Stopped before this one was checked.')).toBeInTheDocument()
  expect(screen.getByText("The model didn't give a usable answer")).toBeInTheDocument()
})

test('queued and running rows are pending, not failures; a done cannot_verify one is', () => {
  show({ items: [
    { ...claim, id: 'q', status: 'queued', verdict: null, sentence_hash: 'q', sentence: 'Queued one.' },
    { ...claim, id: 'r', status: 'running', verdict: null, sentence_hash: 'r', sentence: 'Running one.' },
    item({ id: 'c', sentence_hash: 'c', status: 'queued', verdict: null, reason: null }),
    { ...claim, id: 'd', status: 'done', verdict: 'cannot_verify', reason: 'model_error', sentence_hash: 'd' },
  ] })
  expect(screen.getAllByText('Checking…')).toHaveLength(3)
  expect(screen.getAllByText("Couldn't check")).toHaveLength(1)
  expect(screen.queryByRole('button', { name: 'Find papers' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Not a claim' })).toBeNull()
})
