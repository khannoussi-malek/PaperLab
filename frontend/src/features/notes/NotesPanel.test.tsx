// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeAll, expect, test, vi } from 'vitest'
import { NoteCard } from './NoteCard'
import { TEMPLATE } from './noteKinds'
import { NotesPanel } from './NotesPanel'

vi.mock('./SuggestedNotes', () => ({ SuggestedNotes: () => null }))
vi.mock('../checks/NoteCheck', () => ({ NoteCheck: ({ note }: { note: { id: string } }) => <div>check-slot-{note.id}</div> }))

const props = {
  paperId: 'p1', notes: [], draft: null, draftColor: '#facc15', activeNoteId: null, onDraftColorChange: vi.fn(),
  onSaveDraft: vi.fn(), onCancelDraft: vi.fn(), onAddNumber: vi.fn(), onSelectNote: vi.fn(), onUpdateNote: vi.fn(),
  onColorNote: vi.fn(), onDeleteNote: vi.fn(), movedToNotes: false, onPapersSaved: vi.fn(), onCite: vi.fn(),
  wholePaperDraft: null, onNewPaperNote: vi.fn(), onCancelPaperNote: vi.fn(), onSavePaperNote: vi.fn(),
}

test('a paper without a PDF has a plain composer that saves a note and empties itself', async () => {
  const onSavePaperNote = vi.fn().mockResolvedValue(true)
  render(<NotesPanel {...props} hasPdf={false} hasAbstract onSavePaperNote={onSavePaperNote} />)
  expect(screen.getByText('Select text in the abstract, or write a note.')).toBeInTheDocument()
  expect(screen.queryByText(/Select text in the paper/)).toBeNull()
  const box = screen.getByRole('textbox', { name: 'New note' })
  fireEvent.change(box, { target: { value: 'Read later.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save note' }))
  await waitFor(() => expect(onSavePaperNote).toHaveBeenCalledWith('Read later.', null))
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
  expect(screen.getByText('Select text in the paper to add a note, or')).toBeInTheDocument()
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

const withClient = (ui: React.ReactElement) => (
  <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>
)

const note = (id: string, body: string, kind: string | null) =>
  ({ id, body, kind, provenance: 'human', color: '#facc15', created_at: '2020-01-01T00:00:00Z', anchors: [], paper_ids: ['p1'], charts: [] }) as never

async function pick(trigger: HTMLElement, option: string) {
  fireEvent.keyDown(trigger, { key: 'Enter' })
  fireEvent.click(await screen.findByRole('option', { name: option }))
}

beforeAll(() => {
  Object.assign(Element.prototype, {
    hasPointerCapture: () => false,
    setPointerCapture: () => {},
    releasePointerCapture: () => {},
    scrollIntoView: () => {},
  })
})

test('the kind filter narrows the list and says when nothing matches', async () => {
  const notes = [note('a', 'alpha body', 'summary'), note('b', 'beta body', null)]
  render(withClient(<NotesPanel {...props} notes={notes} />))
  await pick(screen.getByRole('combobox', { name: 'Filter by kind' }), 'Summary')
  expect(screen.getByText('alpha body')).toBeInTheDocument()
  expect(screen.queryByText('beta body')).toBeNull()
  await pick(screen.getByRole('combobox', { name: 'Filter by kind' }), 'Plain notes')
  expect(screen.getByText('beta body')).toBeInTheDocument()
  expect(screen.queryByText('alpha body')).toBeNull()
  await pick(screen.getByRole('combobox', { name: 'Filter by kind' }), 'Figure')
  expect(screen.getByText('No notes match these filters.')).toBeInTheDocument()
})

test('a card shows its kind beside its provenance', () => {
  const { container } = render(withClient(<NotesPanel {...props} notes={[note('a', 'alpha', 'five_cs'), note('b', 'beta', null)]} />))
  const badges = container.querySelectorAll('.note-kind')
  expect(badges).toHaveLength(1)
  expect(badges[0]).toHaveTextContent('Five Cs')
})

test('editing a card can set and clear its kind', async () => {
  const onUpdateNote = vi.fn().mockResolvedValue(true)
  render(withClient(<NotesPanel {...props} onUpdateNote={onUpdateNote} notes={[note('a', 'alpha', null)]} />))
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
  const kind = () => screen.getAllByRole('combobox', { name: 'Kind' }).at(-1)!
  await pick(kind(), 'Summary')
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(onUpdateNote).toHaveBeenLastCalledWith(expect.anything(), 'alpha', 'summary'))
})

test('editing a card can clear its kind: null is sent, not dropped', async () => {
  const onUpdateNote = vi.fn().mockResolvedValue(true)
  render(withClient(<NotesPanel {...props} onUpdateNote={onUpdateNote} notes={[note('a', 'alpha', 'summary')]} />))
  fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
  await pick(screen.getAllByRole('combobox', { name: 'Kind' }).at(-1)!, 'Note')
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(onUpdateNote).toHaveBeenLastCalledWith(expect.anything(), 'alpha', null))
})

const card = (extra: object, onUpdate = vi.fn().mockResolvedValue(true)) =>
  render(
    withClient(
      <NoteCard note={note('a', '', null)} startEditing onUpdate={onUpdate} onColorChange={vi.fn()} onDelete={vi.fn()} {...extra} />,
    ),
  )

test('without editKind a card has no Kind picker and onUpdate gets the body only', async () => {
  const onUpdate = vi.fn().mockResolvedValue(true)
  card({}, onUpdate)
  expect(screen.queryByRole('combobox', { name: 'Kind' })).toBeNull()
  fireEvent.change(screen.getByRole('textbox', { name: 'Edit note' }), { target: { value: 'x' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(onUpdate).toHaveBeenCalledWith('x'))
  expect(onUpdate.mock.calls[0]).toHaveLength(1)
})

test('changing the kind in edit mode swaps an untouched template and keeps typed text', async () => {
  card({ editKind: true })
  const box = screen.getByRole('textbox', { name: 'Edit note' })
  await pick(screen.getByRole('combobox', { name: 'Kind' }), 'Five Cs')
  expect(box).toHaveValue(TEMPLATE.five_cs)
  await pick(screen.getByRole('combobox', { name: 'Kind' }), 'Figure')
  expect(box).toHaveValue(TEMPLATE.figure)
  fireEvent.change(box, { target: { value: 'my own words' } })
  await pick(screen.getByRole('combobox', { name: 'Kind' }), 'Summary')
  expect(box).toHaveValue('my own words')
})

test('the New note button is where the spec says in each composer state: none open', () => {
  const onNewPaperNote = vi.fn()
  render(<NotesPanel {...props} onNewPaperNote={onNewPaperNote} />)
  expect(screen.getByText(/Select text in the paper to add a note, or/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'New note on this paper' }))
  expect(onNewPaperNote).toHaveBeenCalled()
})

test('the New note button is where the spec says in each composer state: selection open', () => {
  render(<NotesPanel {...props} draft={{ page: 1, rects: [[0, 0, 1, 1]], quotedText: 'quoted' }} />)
  expect(screen.getByRole('button', { name: 'New note on this paper' })).toBeInTheDocument()
  expect(screen.queryByText(/Select text in the paper/)).toBeNull()
})

test('the New note button is where the spec says in each composer state: whole-paper open', () => {
  render(<NotesPanel {...props} wholePaperDraft={{ kind: 'summary' }} />)
  expect(screen.queryByRole('button', { name: 'New note on this paper' })).toBeNull()
  expect(screen.getByRole('textbox', { name: 'New note' })).toBeInTheDocument()
  expect(screen.getByText(/the main thrust/i)).toBeInTheDocument()
})

test('each card gets the note check in its check slot', () => {
  const note = { id: 'n1', kind: 'summary', provenance: 'human', body: 'x', anchors: [], color: '#facc15', paper_ids: ['p1'], created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z' }
  render(
    <QueryClientProvider client={new QueryClient()}>
      <NotesPanel {...props} notes={[note as never]} />
    </QueryClientProvider>,
  )
  expect(screen.getByText('check-slot-n1')).toBeInTheDocument()
})

test('Write it with another kind keeps what the reader typed', () => {
  const { rerender } = render(<NotesPanel {...props} wholePaperDraft={{ kind: 'summary' }} />)
  fireEvent.change(screen.getByRole('textbox', { name: 'New note' }), { target: { value: 'My own words' } })
  rerender(<NotesPanel {...props} wholePaperDraft={{ kind: 'reconstruction' }} />)
  expect(screen.getByRole('textbox', { name: 'New note' })).toHaveValue('My own words')
})

test('Write it with another kind swaps an untouched template', () => {
  const { rerender } = render(<NotesPanel {...props} wholePaperDraft={{ kind: 'five_cs' }} />)
  expect(screen.getByRole('textbox', { name: 'New note' })).toHaveValue(TEMPLATE.five_cs)
  rerender(<NotesPanel {...props} wholePaperDraft={{ kind: 'summary' }} />)
  expect(screen.getByRole('textbox', { name: 'New note' })).toHaveValue('')
})

test('on a paper without a PDF, Write it keeps text typed in the always-on composer', () => {
  const { rerender } = render(<NotesPanel {...props} hasPdf={false} />)
  fireEvent.change(screen.getByRole('textbox', { name: 'New note' }), { target: { value: 'Typed first' } })
  rerender(<NotesPanel {...props} hasPdf={false} wholePaperDraft={{ kind: 'summary' }} />)
  expect(screen.getByRole('textbox', { name: 'New note' })).toHaveValue('Typed first')
})
