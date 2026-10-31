// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError } from '@/api/client'
import { RemoteConfirmDialog } from './RemoteConfirm'
import { useReview } from './useReview'
import { useReviewInEditor } from './useReviewInEditor'

afterEach(() => vi.restoreAllMocks())
const remote = () => new ApiError('remote_model_needs_confirm', 409, { detail: 'remote_model_needs_confirm', model: 'Cloud · big', host: 'api.example.com' })

// Check citations as SourcePane wires it: the menu's check, and the confirm the 409 opens.
function Harness() {
  const review = useReview('m', 'main.tex')
  const r = useReviewInEditor({ manuscriptId: 'm', workspaceId: 'w', review, text: 'Alpha.', handle: null, flush: async () => true, getBase: () => 'v1' })
  return (
    <>
      <button type="button" onClick={() => void r.check()}>Check citations</button>
      {review.startError && <p>{review.startError}</p>}
      <RemoteConfirmDialog what="text" host={review.confirmHost} onSend={() => void r.check(true)} onCancel={review.dismissConfirm} />
    </>
  )
}
const show = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><Harness /></QueryClientProvider>)

test('Check citations on a remote model asks first; Send retries with confirm_remote', async () => {
  vi.spyOn(api, 'reviewState').mockResolvedValue({ run: null, items: [], dismissed: [] })
  const start = vi.spyOn(api, 'startReview').mockRejectedValueOnce(remote()).mockResolvedValue({ id: 'r' } as never)
  show()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Check citations' })))
  const dialog = await screen.findByRole('dialog', { name: 'Send to api.example.com?' })
  expect(dialog).toHaveTextContent('Your text will be sent to api.example.com and may cost money. Send it?')
  expect(screen.queryByText(/remote_model_needs_confirm/)).toBeNull() // a question, not an error
  await waitFor(() => expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()) // Enter must not spend money
  expect(start).toHaveBeenLastCalledWith('m', expect.objectContaining({ confirm_remote: false }))
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Send' })))
  await waitFor(() => expect(start).toHaveBeenCalledTimes(2))
  expect(start).toHaveBeenLastCalledWith('m', expect.objectContaining({ file: 'main.tex', base: 'v1', confirm_remote: true }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
})

test('Cancel sends nothing', async () => {
  vi.spyOn(api, 'reviewState').mockResolvedValue({ run: null, items: [], dismissed: [] })
  const start = vi.spyOn(api, 'startReview').mockRejectedValue(remote())
  show()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Check citations' })))
  await screen.findByRole('dialog')
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Cancel' })))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(start).toHaveBeenCalledTimes(1)
})
