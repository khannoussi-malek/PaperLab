// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { ChatSource, Paper } from '@/api/client'
import { ReaderPage, groupHighlights } from './ReaderPage'

type NotesProps = {
  draft: { quotedText: string; figure?: true } | null
  onSaveDraft: (body: string, kind?: string | null) => Promise<boolean>
  onSavePaperNote: (body: string, kind?: string | null) => Promise<boolean>
  wholePaperDraft: { kind: string | null } | null
  onNewPaperNote: () => void
  onPaperNoteDirty?: (dirty: boolean) => void
}
const state = vi.hoisted(() => ({
  paper: undefined as Paper | undefined,
  paperError: null as Error | null,
  onCite: null as null | ((s: ChatSource) => void),
  notes: null as null | NotesProps,
  create: vi.fn(),
  createFigure: vi.fn(),
  onFigure: null as null | ((page: number, region: number[]) => void),
}))
vi.mock('../data/useCaptureDrag', () => ({
  useCaptureDrag: (_scale: number, onFigure: (page: number, region: number[]) => void) => {
    state.onFigure = onFigure
    return { capturing: false, tableMode: false, drawingFigure: false, setCapturing: () => {}, setDrawingFigure: () => {}, box: null, capture: null, closeCapture: () => {}, startDrag: () => {}, moveDrag: () => {}, endDrag: () => {} }
  },
}))
const getDocument = vi.hoisted(() => vi.fn(() => ({ promise: new Promise(() => {}), destroy: vi.fn() })))
vi.mock('./pdfjs', () => ({ getDocument, pdfWorker: null }))
vi.mock('@/api/queries', () => {
  const idle = { data: undefined, error: null }
  return {
    usePaper: () => ({ data: state.paper, error: state.paperError, isError: state.paperError !== null }),
    useNotes: () => ({ data: [], error: null }),
    useNoteMutations: () => ({ create: { mutateAsync: state.create }, createFigure: { mutateAsync: state.createFigure }, update: {}, remove: {} }),
    useChunksOnPage: () => idle,
    usePaperDatasets: () => ({ data: [] }),
    useDataset: () => idle,
    useReferences: () => idle,
  }
})
// The side panel's tabs and the toolbar's menus have their own tests; here they only need to mount.
vi.mock('../chat/ChatPanel', () => ({
  ChatPanel: ({ onCite }: { onCite: (s: ChatSource) => void }) => {
    state.onCite = onCite
    return null
  },
}))
vi.mock('../notes/NotesPanel', () => ({
  NotesPanel: (props: NotesProps) => {
    state.notes = props
    return null
  },
}))
vi.mock('../data/DataPanel', () => ({ DataPanel: () => null }))
vi.mock('../lenses/queries', () => ({
  usePaperSections: () => ({ data: undefined }),
  usePaperChunks: () => ({ data: undefined }),
}))
vi.mock('../lenses/LensPanel', () => ({ LensPanel: () => null }))
vi.mock('../discovery/SimilarTab', () => ({ SimilarTab: () => null }))
vi.mock('../references/ReferencesTab', () => ({ ReferencesTab: () => null }))
vi.mock('../evidence/EvidencePanel', () => ({ EvidencePanel: () => null }))
vi.mock('../library/GetPdfActions', () => ({ GetPdfActions: () => null }))
vi.mock('./PaperTagChips', () => ({ PaperTagChips: () => null }))
vi.mock('./ReadingContextBanner', () => ({ ReadingContextBanner: () => null }))
vi.mock('../reading/ReadingControl', () => ({ ReadingControl: () => null }))
vi.mock('./PaperDetailsDialog', () => ({ PaperDetailsDialog: () => null }))
vi.mock('@/components/mode-toggle', () => ({ ModeToggle: () => null }))
vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

const ID = '6f1c2a40-1111-4a8e-9c4e-000000000001'
const paper = (over: Partial<Paper>) =>
  ({
    id: ID, title: 'Sleep and memory', authors: ['Ada Lee', 'Bo Chen'], year: 2020, venue: 'Sleep Journal',
    doi: '10.1/sleep', abstract: 'Sleep helps memory consolidation.', has_pdf: false, details_source: 'zotero', field_sources: {},
    status: 'ready', evidence_access: 'abstract', source_type: null, peer_reviewed: 'unknown', is_retracted: false,
    published_doi: null, ...over,
  }) as Paper

beforeEach(() => {
  getDocument.mockClear()
  state.paperError = null
  state.create.mockReset().mockResolvedValue({})
})
afterEach(() => { window.location.hash = '' })

const ID2 = ID
beforeEach(() => {
  state.paper = paper({ has_pdf: true })
  state.createFigure.mockReset().mockResolvedValue({})
  state.create.mockReset().mockResolvedValue({})
})
afterEach(() => { window.location.hash = '' })

test('a drawn figure box becomes a figure draft, and saving it calls createFigure, not create', async () => {
  render(<ReaderPage paperId={ID2} tab="notes" target={null} />)
  act(() => state.onFigure!(4, [1, 2, 30, 40]))
  expect(state.notes!.draft).toMatchObject({ figure: true, quotedText: 'Figure on p. 4' })
  await act(async () => void (await state.notes!.onSaveDraft('looks fine')))
  expect(state.createFigure).toHaveBeenCalledWith(expect.objectContaining({ paper_id: ID2, page: 4, region: [1, 2, 30, 40], body: 'looks fine' }))
  expect(state.create).not.toHaveBeenCalled()
})

test('a figure box leaves a composer with typed text alone', () => {
  render(<ReaderPage paperId={ID2} tab="notes" target={null} />)
  act(() => state.notes!.onNewPaperNote())
  act(() => state.notes!.onPaperNoteDirty!(true))
  act(() => state.onFigure!(4, [1, 2, 30, 40]))
  expect(state.notes!.draft).toBeNull()
  expect(state.notes!.wholePaperDraft).toEqual({ kind: null })
  expect(screen.getByText('Save or cancel the note you are writing first.')).toBeInTheDocument()
  act(() => state.notes!.onPaperNoteDirty!(false))
  act(() => state.onFigure!(4, [1, 2, 30, 40])) // untouched: replaced as before
  expect(state.notes!.draft).toMatchObject({ figure: true })
})

test('groupHighlights marks a figure note rect and leaves others unmarked', () => {
  const anchor = (bbox: number[][]) => [{ paper_id: ID2, page: 1, bbox }]
  const notes = [
    { id: 'a', color: '#f00', kind: 'figure', provenance: 'human', anchors: anchor([[1, 2, 3, 4]]) },
    { id: 'b', color: '#0f0', kind: null, provenance: 'human', anchors: anchor([[5, 6, 7, 8]]) },
  ] as never
  const rects = groupHighlights(notes, null, ID2).get(1)!
  expect(rects.map((r) => r.figure)).toEqual([true, false])
})
