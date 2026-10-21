// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { LibraryPage } from './LibraryPage'

const state = vi.hoisted(() => ({ papers: [] as { id: string; title: string }[] }))
vi.mock('@/api/queries', () => ({
  usePapers: () => ({ data: state.papers, isError: false }),
  useUploadPapers: () => ({ isPending: false, error: null, mutate: vi.fn() }),
  useEmbeddingStatus: () => ({ data: undefined }),
}))
vi.mock('@/components/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main> }))
vi.mock('./FoundPdfsNotice', () => ({ FoundPdfsNotice: () => null }))
vi.mock('../discovery/FindPapersButton', () => ({ FindPapersButton: () => null }))
type Selection = { selected: ReadonlySet<string>; onToggle: (id: string) => void }
// The real list pulls in pdfjs, which needs a worker: a checkbox per paper stands in for its rows.
vi.mock('./PaperList', () => ({
  PaperList: ({ papers, selection }: { papers: { id: string; title: string }[]; selection?: Selection }) => (
    <ul>
      {papers.map((p) => (
        <li key={p.id}>
          <input type="checkbox" aria-label={`Select ${p.title}`} checked={selection?.selected.has(p.id) ?? false}
            onChange={() => selection?.onToggle(p.id)} />
        </li>
      ))}
    </ul>
  ),
}))
vi.mock('@/features/graph/viewModel', () => ({ hasWebGL: () => false }))
vi.stubGlobal('matchMedia', () => ({ matches: false }))
afterEach(() => {
  state.papers = []
  vi.restoreAllMocks()
})

test('the empty Library still says what to do, with the icon as the fallback when 3D cannot run', () => {
  render(<LibraryPage />)
  expect(screen.getByText('No papers yet. Upload a PDF, or add one by DOI.')).toBeInTheDocument()
  expect(document.querySelector('svg.lucide-file-text')).not.toBeNull()
  expect(document.querySelector('canvas')).toBeNull()
})

test('ticked papers get a selection bar that exports just them, with no workspace, and Clear empties it', async () => {
  state.papers = [{ id: 'a', title: 'Alpha' }, { id: 'b', title: 'Beta' }, { id: 'c', title: 'Gamma' }]
  const spy = vi.spyOn(api, 'exportSelection').mockResolvedValue({ blob: new Blob(['x']), filename: 'citations.bib' })
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  render(<QueryClientProvider client={new QueryClient()}><LibraryPage /></QueryClientProvider>)
  expect(screen.queryByRole('button', { name: 'Export selected…' })).toBeNull()
  fireEvent.click(screen.getByLabelText('Select Alpha'))
  fireEvent.click(screen.getByLabelText('Select Gamma'))
  expect(screen.getByRole('status').textContent).toBe('2 selected')
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Export selected…' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: 'BibTeX' }))
  await waitFor(() => expect(spy).toHaveBeenCalledWith(['a', 'c'], 'bibtex', undefined))
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
  expect(screen.queryByText('2 selected')).toBeNull()
})
