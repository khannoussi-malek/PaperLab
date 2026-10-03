// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { LibraryPage } from './LibraryPage'

vi.mock('@/api/queries', () => ({
  usePapers: () => ({ data: [], isError: false }),
  useUploadPapers: () => ({ isPending: false, error: null, mutate: vi.fn() }),
  useEmbeddingStatus: () => ({ data: undefined }),
}))
vi.mock('@/components/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main> }))
vi.mock('../discovery/FindPapersButton', () => ({ FindPapersButton: () => null }))
vi.mock('./PaperList', () => ({ PaperList: () => null })) // pulls in pdfjs, which needs a worker
vi.mock('@/features/graph/viewModel', () => ({ hasWebGL: () => false }))
vi.stubGlobal('matchMedia', () => ({ matches: false }))

test('the empty Library still says what to do, with the icon as the fallback when 3D cannot run', () => {
  render(<LibraryPage />)
  expect(screen.getByText('No papers yet. Upload a PDF to start.')).toBeInTheDocument()
  expect(document.querySelector('svg.lucide-file-text')).not.toBeNull()
  expect(document.querySelector('canvas')).toBeNull()
})
