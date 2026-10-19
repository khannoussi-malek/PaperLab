// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { NotesPanel } from './NotesPanel'

vi.mock('./SuggestedNotes', () => ({ SuggestedNotes: () => null }))

const props = {
  paperId: 'p1', notes: [], draft: null, draftColor: '#facc15', activeNoteId: null, onDraftColorChange: vi.fn(),
  onSaveDraft: vi.fn(), onCancelDraft: vi.fn(), onAddNumber: vi.fn(), onSelectNote: vi.fn(), onUpdateNote: vi.fn(),
  onColorNote: vi.fn(), onDeleteNote: vi.fn(), movedToNotes: false, onPapersSaved: vi.fn(),
}

test('a paper without a PDF has a plain composer that saves a note and empties itself', async () => {
  const onSavePaperNote = vi.fn().mockResolvedValue(true)
  render(<NotesPanel {...props} hasPdf={false} hasAbstract onSavePaperNote={onSavePaperNote} />)
  expect(screen.getByText('Select text in the abstract, or write a note.')).toBeInTheDocument()
  expect(screen.queryByText(/Select text in the paper/)).toBeNull()
  const box = screen.getByRole('textbox', { name: 'New note' })
  fireEvent.change(box, { target: { value: 'Read later.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save note' }))
  await waitFor(() => expect(onSavePaperNote).toHaveBeenCalledWith('Read later.'))
  await waitFor(() => expect(box).toHaveValue(''))
})

test('a draft from the abstract shows its quote, with no Add as number', () => {
  render(<NotesPanel {...props} hasPdf={false} onSavePaperNote={vi.fn()} draft={{ page: 0, rects: [], quotedText: 'Sleep helps memory' }} />)
  expect(screen.getByText('Sleep helps memory')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Add as number/ })).toBeNull()
  expect(screen.queryByRole('textbox', { name: 'New note' })).toBeNull()
})

test('a paper with a PDF keeps its prompt and has no plain composer', () => {
  render(<NotesPanel {...props} />)
  expect(screen.getByText('Select text in the paper to add a note.')).toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: 'New note' })).toBeNull()
})

test('a paper without a PDF or an abstract only offers to write a note', () => {
  render(<NotesPanel {...props} hasPdf={false} hasAbstract={false} onSavePaperNote={vi.fn()} />)
  expect(screen.getByText('Write a note.')).toBeInTheDocument()
  expect(screen.queryByText(/Select text/)).toBeNull()
  expect(screen.getByRole('textbox', { name: 'New note' })).toBeInTheDocument()
})

test('each new selection in the abstract starts its composer empty', () => {
  const draft = (quotedText: string) => ({ page: 0, rects: [], quotedText })
  const { rerender } = render(<NotesPanel {...props} hasPdf={false} hasAbstract onSavePaperNote={vi.fn()} draft={draft('Sleep helps')} />)
  fireEvent.change(screen.getByRole('textbox', { name: 'Note' }), { target: { value: 'half-written' } })
  rerender(<NotesPanel {...props} hasPdf={false} hasAbstract onSavePaperNote={vi.fn()} draft={draft('memory consolidation')} />)
  expect(screen.getByText('memory consolidation')).toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: 'Note' })).toHaveValue('')
})
