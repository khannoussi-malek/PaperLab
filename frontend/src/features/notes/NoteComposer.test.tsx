// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeAll, expect, test, vi } from 'vitest'
import { KIND_HINT, TEMPLATE } from './noteKinds'
import { NoteComposer, PlainNoteComposer } from './NoteComposer'

beforeAll(() => {
  Object.assign(Element.prototype, {
    hasPointerCapture: () => false,
    setPointerCapture: () => {},
    releasePointerCapture: () => {},
    scrollIntoView: () => {},
  })
})

async function pick(option: string) {
  fireEvent.keyDown(screen.getByRole('combobox', { name: 'Kind' }), { key: 'Enter' })
  fireEvent.click(await screen.findByRole('option', { name: option }))
}

test('picking Five Cs in an empty composer fills the headings', async () => {
  render(<PlainNoteComposer onSave={vi.fn()} />)
  await pick('Five Cs')
  expect(screen.getByRole('textbox', { name: 'New note' })).toHaveValue(TEMPLATE.five_cs)
})

test('switching kind replaces an untouched template and never typed text', async () => {
  render(<PlainNoteComposer onSave={vi.fn()} />)
  await pick('Five Cs')
  await pick('Summary')
  expect(screen.getByRole('textbox', { name: 'New note' })).toHaveValue('')
  fireEvent.change(screen.getByRole('textbox', { name: 'New note' }), { target: { value: 'my words' } })
  await pick('Five Cs')
  expect(screen.getByRole('textbox', { name: 'New note' })).toHaveValue('my words')
})

test('the hint follows the kind', async () => {
  render(<PlainNoteComposer onSave={vi.fn()} initialKind="summary" />)
  expect(screen.getByText(KIND_HINT.summary)).toBeInTheDocument()
  await pick('Reconstruction')
  expect(screen.getByText(KIND_HINT.reconstruction)).toBeInTheDocument()
  expect(screen.queryByText(KIND_HINT.summary)).toBeNull()
})

test('saving sends the kind', async () => {
  const onSave = vi.fn().mockResolvedValue(true)
  render(<PlainNoteComposer onSave={onSave} />)
  await pick('Summary')
  fireEvent.change(screen.getByRole('textbox', { name: 'New note' }), { target: { value: 'It works.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save note' }))
  await waitFor(() => expect(onSave).toHaveBeenCalledWith('It works.', 'summary'))
})

test('a selection composer sends the kind too, and Cancel shows only when asked for', async () => {
  const onSave = vi.fn().mockResolvedValue(true)
  const draft = { page: 0, rects: [], quotedText: 'q' }
  const props = { draft, color: '#facc15', onColorChange: vi.fn(), onSave, onCancel: vi.fn(), onAddNumber: vi.fn() }
  render(<NoteComposer {...props} />)
  await pick('Summary')
  fireEvent.click(screen.getByRole('button', { name: 'Save note' }))
  await waitFor(() => expect(onSave).toHaveBeenCalledWith('', 'summary'))
})

test('the whole-paper composer has Cancel only with onCancel, and no Save for an empty body', () => {
  const { rerender } = render(<PlainNoteComposer onSave={vi.fn()} />)
  expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Save note' })).toBeDisabled()
  rerender(<PlainNoteComposer onSave={vi.fn()} onCancel={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
})

test('a figure draft is kind Figure with its questions, and has no Add as number', async () => {
  const onSave = vi.fn().mockResolvedValue(true)
  const draft = { page: 2, rects: [[1, 2, 30, 40]] as [number, number, number, number][], quotedText: 'Figure on p. 2', figure: true as const }
  render(<NoteComposer draft={draft} color="#facc15" onColorChange={vi.fn()} onSave={onSave} onCancel={vi.fn()} onAddNumber={vi.fn()} />)
  expect(screen.getByRole('textbox', { name: 'Note' })).toHaveValue(TEMPLATE.figure)
  expect(screen.getByRole('combobox', { name: 'Kind' })).toHaveTextContent('Figure')
  expect(screen.queryByRole('button', { name: 'Add as number' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Save note' }))
  await waitFor(() => expect(onSave).toHaveBeenCalledWith(TEMPLATE.figure, 'figure'))
})
