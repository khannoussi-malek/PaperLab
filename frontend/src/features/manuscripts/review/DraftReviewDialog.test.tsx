// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, type DraftReview, type DraftReviewEstimate } from '@/api/client'
import { DraftReviewDialog } from './DraftReviewDialog'

const estimate: DraftReviewEstimate = {
  paper_chars: 9000,
  too_long: false,
  modes: [
    { mode: 'light', likely_calls: 8, max_calls: 11, approx_input_tokens: 9000 },
    { mode: 'full', likely_calls: 42, max_calls: 54, approx_input_tokens: 90000 },
  ],
}
const review = (o: Partial<DraftReview> = {}): DraftReview => ({
  id: 'r1', mode: 'light', status: 'done', stage: null, calls_done: 0, calls_max: 11, reason: null,
  issues: [], refuted: [], counts: {}, model: 'local', ai: true, created_at: '2026-11-11T10:00:00Z', ...o,
})
const remote = new ApiError('remote_model_needs_confirm', 409, { detail: 'remote_model_needs_confirm', model: 'Cloud · big', host: 'api.example.com' })
const fullConfirm = new ApiError('full_needs_confirm', 409, { detail: 'full_needs_confirm' })

beforeEach(() => {
  vi.spyOn(api, 'draftReviewEstimate').mockResolvedValue(estimate)
  vi.spyOn(api, 'draftReview').mockResolvedValue({ review: null })
  vi.spyOn(api, 'startDraftReview').mockResolvedValue(review({ status: 'queued' }))
  vi.spyOn(api, 'cancelDraftReview').mockResolvedValue(review({ status: 'failed', reason: 'cancelled' }))
})
afterEach(() => { vi.restoreAllMocks() })

function show(onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><DraftReviewDialog manuscriptId="m" open onClose={onClose} /></QueryClientProvider>)
  return { onClose }
}
const start = () => act(async () => fireEvent.click(screen.getByRole('button', { name: /^Start (full )?review$/ })))
const serve = (r: DraftReview) => vi.mocked(api.draftReview).mockResolvedValue({ review: r })

test('both estimates show before anything starts, Light is selected, and Start review sends the light body', async () => {
  show()
  expect(screen.getByRole('dialog', { name: 'Tough draft review' })).toBeInTheDocument()
  expect(screen.getByText('AI review')).toBeInTheDocument()
  expect(await screen.findByText('Light: up to 11 model calls, about 10 to 15 minutes on a local model.')).toBeInTheDocument()
  expect(screen.getByText('Full: about 42 model calls, at most 54, up to an hour or more on a local model.')).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: /Light/ })).toBeChecked()
  await start()
  expect(api.startDraftReview).toHaveBeenCalledWith('m', { mode: 'light', confirm_remote: false, confirm_full: false })
})

test('Full shows its own button, opens a confirm step with Cancel focused, and Run sends the full body', async () => {
  show()
  await screen.findByText(/about 42 model calls/)
  fireEvent.click(screen.getByRole('radio', { name: /Full/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Start full review' }))
  expect(screen.getByText('This runs about 42 model calls, at most 54. Run it?')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
  expect(api.startDraftReview).not.toHaveBeenCalled()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Run' })))
  expect(api.startDraftReview).toHaveBeenCalledWith('m', { mode: 'full', confirm_remote: false, confirm_full: true })
})

test('a server full_needs_confirm opens the same confirm step', async () => {
  vi.mocked(api.startDraftReview).mockRejectedValueOnce(fullConfirm)
  show()
  await screen.findByText(/about 42 model calls/)
  await start()
  expect(await screen.findByText('This runs about 42 model calls, at most 54. Run it?')).toBeInTheDocument()
})

test('a remote model asks first with RemoteConfirm; Send retries with confirm_remote', async () => {
  vi.mocked(api.startDraftReview).mockRejectedValueOnce(remote)
  show()
  await screen.findByText(/about 42 model calls/)
  await start()
  expect(await screen.findByText('Your text will be sent to api.example.com and may cost money. Send it?')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Send' })))
  expect(api.startDraftReview).toHaveBeenLastCalledWith('m', { mode: 'light', confirm_remote: true, confirm_full: false })
})

test('a running review shows its stage, calls done of max, and Cancel calls cancelDraftReview', async () => {
  serve(review({ status: 'running', stage: 'Skeptics', calls_done: 3, calls_max: 11 }))
  show()
  expect(await screen.findByText('Skeptics')).toBeInTheDocument()
  expect(screen.getByText('3 of 11 calls')).toBeInTheDocument()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Cancel' })))
  expect(api.cancelDraftReview).toHaveBeenCalledWith('m', 'r1')
})

test('a done review lists each issue with its severity, section, summary, quote, criterion and place', async () => {
  serve(review({
    counts: { rounds_run: 1 },
    issues: [{ id: 'I-01', severity: 'major', section: 'Introduction', summary: 'Claim outruns evidence', quote: 'we prove it works', close_criterion: 'A table reports the test', raised_by: ['a'], file: 'main.tex', line: 12 }],
  }))
  show()
  const card = await screen.findByRole('list', { name: 'Issues' })
  expect(within(card).getByText('Major')).toBeInTheDocument()
  expect(within(card).getByText('Introduction')).toBeInTheDocument()
  expect(within(card).getByText('Claim outruns evidence')).toBeInTheDocument()
  expect(within(card).getByText('we prove it works', { selector: 'blockquote' })).toBeInTheDocument()
  expect(within(card).getByText('Done when')).toBeInTheDocument()
  expect(within(card).getByText('A table reports the test')).toBeInTheDocument()
  expect(within(card).getByText('main.tex:12')).toBeInTheDocument()
  expect(screen.getByText('Light, 1 round')).toBeInTheDocument()
  expect(screen.queryByText(/suggest|instead/i)).toBeNull()
})

test('refuted issues sit in a collapsed Dismissed by the skeptic list', async () => {
  serve(review({ refuted: [{ summary: 'Old claim', reason: 'Already fixed' }] }))
  show()
  const toggle = await screen.findByText('Dismissed by the skeptic (1)')
  expect(toggle.closest('details')).not.toHaveAttribute('open')
  expect(toggle.closest('details')).toHaveTextContent('Old claim')
})

test('zero issues says so, with the model caveat', async () => {
  serve(review())
  show()
  expect(await screen.findByText("No issues found. This is a model's read, not a guarantee.")).toBeInTheDocument()
})

test('a failed review shows its reason and Start again', async () => {
  serve(review({ status: 'failed', reason: 'model_error' }))
  show()
  expect(await screen.findByText("The model's answer could not be used. Try again.")).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Start again' })).toBeInTheDocument()
})

test('an interrupted review offers Start again', async () => {
  serve(review({ status: 'interrupted' }))
  show()
  expect(await screen.findByRole('button', { name: 'Start again' })).toBeInTheDocument()
})

test('the discard footer counts only the four discard counters', async () => {
  serve(review({ counts: { dropped_invalid: 2, dropped_criterion: 1, dropped_quote: 1, dropped_wording: 0, dropped_seen: 9 } }))
  show()
  expect(await screen.findByText('4 model points were discarded (no exact quote, no close criterion, or wording)')).toBeInTheDocument()
})

test('no discard footer when nothing was discarded', async () => {
  serve(review({ counts: { dropped_seen: 5, over_cap: 2, reasons_masked: 1 } }))
  show()
  await screen.findByText("No issues found. This is a model's read, not a guarantee.")
  expect(screen.queryByText(/were discarded/)).toBeNull()
})

test('a too-long draft disables Start and says so', async () => {
  vi.mocked(api.draftReviewEstimate).mockResolvedValue({ ...estimate, too_long: true })
  show()
  expect(await screen.findByText('The draft is too long to review at once.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Start review' })).toBeDisabled()
})

test('Close closes the dialog without starting', async () => {
  const { onClose } = show()
  await screen.findByText(/about 42 model calls/)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onClose).toHaveBeenCalled()
  expect(api.startDraftReview).not.toHaveBeenCalled()
})
