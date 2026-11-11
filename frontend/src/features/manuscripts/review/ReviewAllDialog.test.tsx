// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError } from '@/api/client'
import { ReviewAllDialog } from './ReviewAllDialog'

const estimate = (pairs: number) => ({
  files: [{ path: 'main.tex', pairs: pairs - 2, uncited: 0 }, { path: 'intro.tex', pairs: 2, uncited: 0 }],
  pairs, uncited: 0, uncited_skipped: 0, confirm_above: 30, max_pairs: 600, needs_confirm: pairs > 30,
})
const posted = (confirmRemote: boolean, confirmLarge: boolean) => ({ include_uncited: true, confirm_remote: confirmRemote, confirm_large: confirmLarge })

function show(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={qc}><ReviewAllDialog open manuscriptId="m" onClose={onClose} /></QueryClientProvider>)
  return { onClose }
}
const runButton = (n: number) => screen.findByRole('button', { name: `Run ${n} checks` })

afterEach(() => vi.restoreAllMocks())

test('a labelled dialog shows the estimate with each file\'s checks', async () => {
  vi.spyOn(api, 'reviewEstimate').mockResolvedValue(estimate(12))
  show()
  expect(screen.getByRole('dialog', { name: 'Review all files' })).toBeInTheDocument()
  expect(await screen.findByText('12 checks across 2 files')).toBeInTheDocument()
  expect(screen.getByText('main.tex: 10 checks')).toBeInTheDocument()
  expect(screen.getByText('intro.tex: 2 checks')).toBeInTheDocument()
  expect(screen.queryByText(/long time/)).not.toBeInTheDocument()
})

test('at 30 checks it starts without the large-run confirm', async () => {
  vi.spyOn(api, 'reviewEstimate').mockResolvedValue(estimate(30))
  const start = vi.spyOn(api, 'startReviewAll').mockResolvedValue({} as never)
  const { onClose } = show()
  fireEvent.click(await runButton(30))
  await waitFor(() => expect(onClose).toHaveBeenCalled())
  expect(start).toHaveBeenCalledWith('m', posted(false, false))
})

test('above 30 it says the run can take a long time on a local model and posts with confirm_large', async () => {
  vi.spyOn(api, 'reviewEstimate').mockResolvedValue(estimate(45))
  const start = vi.spyOn(api, 'startReviewAll').mockResolvedValue({} as never)
  show()
  expect(await screen.findByText(/can take a long time on a local model/)).toBeInTheDocument()
  fireEvent.click(await runButton(45))
  await waitFor(() => expect(start).toHaveBeenCalledWith('m', posted(false, true)))
})

test('a remote model asks first, then posts again with confirm_remote', async () => {
  vi.spyOn(api, 'reviewEstimate').mockResolvedValue(estimate(12))
  const start = vi.spyOn(api, 'startReviewAll')
    .mockRejectedValueOnce(new ApiError('remote_model_needs_confirm', 409, { detail: 'remote_model_needs_confirm', host: 'api.example.com' }))
    .mockResolvedValueOnce({} as never)
  const { onClose } = show()
  fireEvent.click(await runButton(12))
  expect(await screen.findByText('Your text will be sent to api.example.com and may cost money. Send it?')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
  await waitFor(() => expect(onClose).toHaveBeenCalled())
  expect(start).toHaveBeenLastCalledWith('m', posted(true, false))
})

test.each([
  ['too_many_claims', 'More than 600 checks. Review fewer files.'],
  ['no_tex', 'There are no .tex files to review.'],
  ['review_running', 'A check is already running.'],
])('%s shows readable text and stays open', async (code, text) => {
  vi.spyOn(api, 'reviewEstimate').mockResolvedValue(estimate(12))
  vi.spyOn(api, 'startReviewAll').mockRejectedValue(new ApiError(code, 409, { detail: code }))
  const { onClose } = show()
  fireEvent.click(await runButton(12))
  expect(await screen.findByRole('alert')).toHaveTextContent(text)
  expect(onClose).not.toHaveBeenCalled()
})

test('when the estimate cannot be counted it says so', async () => {
  vi.spyOn(api, 'reviewEstimate').mockRejectedValue(new Error('down'))
  show()
  expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't count the checks. Close and try again.")
})

test('Cancel closes without starting', async () => {
  vi.spyOn(api, 'reviewEstimate').mockResolvedValue(estimate(12))
  const start = vi.spyOn(api, 'startReviewAll')
  const { onClose } = show()
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
  expect(onClose).toHaveBeenCalled()
  expect(start).not.toHaveBeenCalled()
})
