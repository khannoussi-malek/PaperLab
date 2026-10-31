// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ApiError, type SectionSpan } from '@/api/client'
import { SectionReviewDialog } from './SectionReviewDialog'

const span = (o: Partial<SectionSpan> = {}): SectionSpan => ({ title: 'Our approach', start: 0, end: 50, hash: 'h', words: 40, guess: 'method', ...o })
const remote = new ApiError('remote_model_needs_confirm', 409, { detail: 'remote_model_needs_confirm', model: 'Cloud · big', host: 'api.example.com' })
function show(section: SectionSpan | null, onStart = vi.fn(async () => {}), onClose = vi.fn(), gone = false) {
  render(<SectionReviewDialog target={{ section, gone }} onStart={onStart} onClose={onClose} />)
  return { onStart, onClose }
}
const select = () => screen.getByRole('combobox', { name: 'Review “Our approach” as:' })

test('a labelled dialog with the guessed role picked; Review keeps the guess (no role sent) and closes', async () => {
  const { onStart, onClose } = show(span())
  expect(screen.getByRole('dialog', { name: 'Review this section' })).toBeInTheDocument()
  expect(select()).toHaveValue('method')
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Review' })))
  expect(onStart).toHaveBeenCalledWith(null, false)
  expect(onClose).toHaveBeenCalled()
})

test('no guess: the select is empty, Review is disabled and it says why; picking a role sends it', async () => {
  const { onStart } = show(span({ guess: null }))
  expect(select()).toHaveValue('')
  expect(screen.getByText("PaperLab couldn't tell what kind of section this is — choose one.")).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Review' })).toBeDisabled()
  fireEvent.change(select(), { target: { value: 'results' } })
  expect(screen.getByRole('button', { name: 'Review' })).toBeEnabled()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Review' })))
  expect(onStart).toHaveBeenCalledWith('results', false)
})

test('a guess of back or other matter counts as no guess', () => {
  show(span({ guess: 'back' }))
  expect(select()).toHaveValue('')
  expect(screen.getByRole('button', { name: 'Review' })).toBeDisabled()
})

test('a remote model asks first: Send retries with confirm_remote', async () => {
  const onStart = vi.fn().mockRejectedValueOnce(remote).mockResolvedValue(undefined)
  const { onClose } = show(span(), onStart)
  fireEvent.change(select(), { target: { value: 'discussion' } })
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Review' })))
  expect(await screen.findByText('Your section will be sent to api.example.com and may cost money. Send it?')).toBeInTheDocument()
  expect(onClose).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus() // Enter must not spend money
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Send' })))
  expect(onStart).toHaveBeenLastCalledWith('discussion', true)
  await waitFor(() => expect(onClose).toHaveBeenCalled())
})

test('Cancel at the remote question sends nothing more', async () => {
  const onStart = vi.fn().mockRejectedValue(remote)
  const { onClose } = show(span(), onStart)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Review' })))
  await screen.findByText(/may cost money/)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Cancel' })))
  expect(onStart).toHaveBeenCalledTimes(1)
  expect(onClose).toHaveBeenCalled()
})

test('a start error stays in the dialog in plain words', async () => {
  show(span(), vi.fn().mockRejectedValue(new ApiError('x', 422, { detail: 'section_too_long' })))
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Review' })))
  expect(await screen.findByRole('alert')).toHaveTextContent('That section is too long to review at once. Review it in parts.')
})

test('outside any section it says so and offers no Review', () => {
  show(null)
  expect(screen.getByText('Put the cursor inside a section first.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Review' })).toBeNull()
})

test('Escape closes it', async () => {
  const { onClose } = show(span())
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
  await waitFor(() => expect(onClose).toHaveBeenCalled())
})

test('Review again on a section that is gone says so', () => {
  show(null, undefined, undefined, true)
  expect(screen.getByText("That section isn't in the file any more.")).toBeInTheDocument()
  expect(screen.queryByText('Put the cursor inside a section first.')).toBeNull()
})
