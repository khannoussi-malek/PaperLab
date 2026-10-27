// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { PdfEditBox } from './PdfEditBox'

const anchor = { left: 10, right: 40, top: 10, bottom: 20, width: 30, height: 10 } as DOMRect
const setup = (over: Partial<Parameters<typeof PdfEditBox>[0]> = {}) => {
  const props = { anchor, initial: 'Dogs bark.', onSave: vi.fn().mockResolvedValue(undefined), onCancel: vi.fn(), onOpenSource: vi.fn(), ...over }
  render(<section><div aria-label="PDF pages" tabIndex={0} /><PdfEditBox {...props} /></section>)
  return { props, box: screen.queryByRole('textbox', { name: 'Edit this text' }) as HTMLElement }
}

test('Enter saves the text and focus goes back to the PDF', async () => {
  const { props, box } = setup()
  expect(box).toHaveValue('Dogs bark.')
  fireEvent.change(box, { target: { value: 'Cats purr.' } })
  fireEvent.keyDown(box, { key: 'Enter' })
  await waitFor(() => expect(props.onSave).toHaveBeenCalledWith('Cats purr.'))
  await waitFor(() => expect(screen.getByLabelText('PDF pages')).toHaveFocus())
})

test('Shift+Enter is a new line, not a save', () => {
  const { props, box } = setup()
  fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
  expect(props.onSave).not.toHaveBeenCalled()
})

test('Esc and Cancel cancel and return focus', () => {
  const { props, box } = setup()
  fireEvent.keyDown(box, { key: 'Escape' })
  expect(props.onCancel).toHaveBeenCalledOnce()
  expect(screen.getByLabelText('PDF pages')).toHaveFocus()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(props.onCancel).toHaveBeenCalledTimes(2)
})

test('a failed save shows its message and keeps the box', async () => {
  const { box } = setup({ onSave: vi.fn().mockRejectedValue(new Error('This file changed since.')) })
  fireEvent.keyDown(box, { key: 'Enter' })
  expect(await screen.findByRole('alert')).toHaveTextContent('This file changed since.')
  expect(screen.getByRole('textbox', { name: 'Edit this text' })).toBeInTheDocument()
})

test('Open in source', () => {
  const { props } = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Open in source' }))
  expect(props.onOpenSource).toHaveBeenCalledOnce()
})

test('a notice replaces the editor', () => {
  setup({ notice: 'Made by LaTeX.' })
  expect(screen.getByText('Made by LaTeX.')).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).toBeNull()
  expect(screen.getByRole('button', { name: 'Open in source' })).toBeInTheDocument()
})
