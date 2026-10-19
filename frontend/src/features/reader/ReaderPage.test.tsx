// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { ChatSource, Paper } from '@/api/client'
import { ReaderPage } from './ReaderPage'

type NotesProps = {
  draft: { quotedText: string } | null
  onSaveDraft: (body: string) => Promise<boolean>
  onSavePaperNote: (body: string) => Promise<boolean>
}
const state = vi.hoisted(() => ({
  paper: undefined as Paper | undefined,
  onCite: null as null | ((s: ChatSource) => void),
  notes: null as null | NotesProps,
  create: vi.fn(),
}))
const getDocument = vi.hoisted(() => vi.fn(() => ({ promise: new Promise(() => {}), destroy: vi.fn() })))
vi.mock('./pdfjs', () => ({ getDocument, pdfWorker: null }))
vi.mock('@/api/queries', () => {
  const idle = { data: undefined, error: null }
  return {
    usePaper: () => ({ data: state.paper, error: null }),
    useNotes: () => ({ data: [], error: null }),
    useNoteMutations: () => ({ create: { mutateAsync: state.create }, update: {}, remove: {} }),
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
vi.mock('../discovery/SimilarTab', () => ({ SimilarTab: () => null }))
vi.mock('../references/ReferencesTab', () => ({ ReferencesTab: () => null }))
vi.mock('../evidence/EvidencePanel', () => ({ EvidencePanel: () => null }))
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
    doi: '10.1/sleep', abstract: 'Sleep helps memory consolidation.', has_pdf: false, details_source: 'zotero',
    status: 'ready', evidence_access: 'abstract', source_type: null, peer_reviewed: 'unknown', is_retracted: false,
    published_doi: null, ...over,
  }) as Paper

beforeEach(() => {
  getDocument.mockClear()
  state.create.mockReset().mockResolvedValue({})
})
afterEach(() => { window.location.hash = '' })

test('a paper without a PDF never asks for its file and shows its details where the pages go', () => {
  state.paper = paper({})
  render(<ReaderPage paperId={ID} tab="notes" target={null} />)
  expect(getDocument).not.toHaveBeenCalled()
  const details = screen.getByRole('region', { name: 'Paper details' })
  expect(details).toHaveTextContent('Sleep and memory')
  expect(details).toHaveTextContent('No PDF yet')
  expect(screen.getByText('Details from Zotero import')).toBeInTheDocument()
  expect(details).toHaveTextContent('Ada Lee, Bo Chen')
  expect(details).toHaveTextContent('2020 · Sleep Journal')
  expect(screen.getByRole('link', { name: 'doi:10.1/sleep' })).toHaveAttribute('href', 'https://doi.org/10.1%2Fsleep')
  expect(screen.getByText('Sleep helps memory consolidation.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Zoom in' })).toBeNull()
  expect(screen.queryByRole('button', { name: /Capture table/ })).toBeNull()
  expect(screen.getByRole('tab', { name: 'Notes' })).toBeInTheDocument()
  expect(screen.queryByRole('alert')).toBeNull()
})

test('a chat link to its abstract (page 0) is dropped from the address instead of waiting on a page', () => {
  state.paper = paper({})
  window.location.hash = `#/papers/${ID}?chunk=6f1c2a40-2222-4a8e-9c4e-000000000002&page=0`
  render(<ReaderPage paperId={ID} tab="notes" target={null} />)
  expect(window.location.hash).toBe(`#/papers/${ID}`)
})

test('a chat citation of the abstract brings the abstract into view', () => {
  state.paper = paper({})
  const scrolled = vi.fn()
  Element.prototype.scrollIntoView = scrolled
  render(<ReaderPage paperId={ID} tab="chat" target={null} />)
  state.onCite!({ label: 'C1', chunk_id: 'c', paper_id: ID, page: 0, section: 'Abstract', bbox: [], from_abstract: true })
  expect(scrolled).toHaveBeenCalled()
  expect(scrolled.mock.contexts[0]).toBe(screen.getByText('Sleep helps memory consolidation.'))
})

test('a paper with a PDF still opens it, with zoom', () => {
  state.paper = paper({ has_pdf: true, evidence_access: 'full_text' })
  render(<ReaderPage paperId={ID} tab="notes" target={null} />)
  expect(getDocument).toHaveBeenCalledWith({ url: `/api/papers/${ID}/file`, worker: null })
  expect(screen.queryByRole('region', { name: 'Paper details' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Zoom in' })).toBeInTheDocument()
})

test('text selected in the abstract becomes the draft, and saving it sends the paper and that exact quote', async () => {
  state.paper = paper({})
  render(<ReaderPage paperId={ID} tab="notes" target={null} />)
  const abstract = screen.getByText('Sleep helps memory consolidation.')
  const range = document.createRange()
  range.setStart(abstract.firstChild!, 0)
  range.setEnd(abstract.firstChild!, 'Sleep helps memory'.length)
  window.getSelection()!.removeAllRanges()
  window.getSelection()!.addRange(range)
  fireEvent.mouseUp(abstract)
  await waitFor(() => expect(state.notes!.draft?.quotedText).toBe('Sleep helps memory'))
  await act(() => state.notes!.onSaveDraft('Key claim.'))
  expect(state.create).toHaveBeenCalledWith({ body: 'Key claim.', color: expect.any(String), paper_id: ID, quote: 'Sleep helps memory' })
})

test('a plain note on a paper without a PDF is saved linked to it, with no anchor', async () => {
  state.paper = paper({})
  render(<ReaderPage paperId={ID} tab="notes" target={null} />)
  await act(() => state.notes!.onSavePaperNote('Read later.'))
  expect(state.create).toHaveBeenCalledWith({ body: 'Read later.', color: expect.any(String), paper_id: ID })
})
