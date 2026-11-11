// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type NoveltyResult } from '@/api/client'
import { readerHref } from '@/lib/route'
import { LibraryPage } from './LibraryPage'
import { NoveltyPanel } from './NoveltyPanel'

// The page test needs the library shell stubbed, as LibraryPage.test.tsx does: the real list pulls in pdfjs and the theme.
vi.mock('@/components/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main> }))
vi.mock('./PaperList', () => ({ PaperList: () => null }))
vi.mock('./FoundPdfsNotice', () => ({ FoundPdfsNotice: () => null }))
vi.mock('../discovery/FindPapersButton', () => ({ FindPapersButton: () => null }))
vi.mock('@/features/graph/viewModel', () => ({ hasWebGL: () => false }))
vi.mock('@/api/queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/queries')>()),
  usePapers: () => ({ data: [], isError: false }),
  useUploadPapers: () => ({ isPending: false, error: null, mutate: vi.fn() }),
  useManuscripts: () => ({ data: undefined }),
}))
vi.stubGlobal('matchMedia', () => ({ matches: false }))

const PAPER = '11111111-1111-1111-1111-111111111111'
const CHUNK = '22222222-2222-2222-2222-222222222222'
const NOTE = 'Only your library was checked: 12 papers.'
const hit = (over: Partial<NoveltyResult['papers'][number]> = {}): NoveltyResult['papers'][number] => ({
  paper_id: PAPER,
  title: 'Alpha on Graphs',
  year: 2020,
  label: 'very close',
  distance: 0.12,
  passage: 'We propose a graph-based method for X.',
  page: 4,
  section: null,
  from_abstract: false,
  chunk_id: CHUNK,
  ...over,
})

const renderPanel = () =>
  render(<QueryClientProvider client={new QueryClient()}><NoveltyPanel /></QueryClientProvider>)
const idea = () => screen.getByLabelText('Paste an idea or an abstract')
const check = () => screen.getByRole('button', { name: 'Check' })

afterEach(() => {
  vi.restoreAllMocks()
})

test('Check stays disabled until the idea has text', () => {
  renderPanel()
  expect(check()).toBeDisabled()
  fireEvent.change(idea(), { target: { value: '   ' } })
  expect(check()).toBeDisabled()
  fireEvent.change(idea(), { target: { value: 'A graph method for X' } })
  expect(check()).toBeEnabled()
})

test('a check posts the text and lists each paper with its label, page and passage', async () => {
  const spy = vi.spyOn(api, 'novelty').mockResolvedValue({ papers: [hit(), hit({ title: 'Beta', label: 'distant', page: null, from_abstract: true, passage: 'An abstract line.' })], searched_papers: 12, note: NOTE })
  renderPanel()
  fireEvent.change(idea(), { target: { value: 'A graph method for X' } })
  fireEvent.click(check())
  await waitFor(() => expect(spy).toHaveBeenCalledWith('A graph method for X'))
  expect(await screen.findByRole('link', { name: 'Alpha on Graphs' })).toHaveAttribute('href', readerHref(PAPER))
  expect(screen.getByText('very close')).toBeInTheDocument()
  expect(screen.getByText('p. 4')).toBeInTheDocument()
  expect(screen.getByText('We propose a graph-based method for X.')).toBeInTheDocument()
  expect(screen.getByText('distant')).toBeInTheDocument()
  expect(screen.getByText('abstract')).toBeInTheDocument()
  expect(screen.getByText('An abstract line.')).toBeInTheDocument()
})

test('the library-only note is shown with an empty result too', async () => {
  vi.spyOn(api, 'novelty').mockResolvedValue({ papers: [], searched_papers: 12, note: NOTE })
  renderPanel()
  fireEvent.change(idea(), { target: { value: 'Something new' } })
  fireEvent.click(check())
  expect(await screen.findByText('Nothing close in your library')).toBeInTheDocument()
  expect(screen.getByText(NOTE)).toBeInTheDocument()
})

test('a failed check shows the error message', async () => {
  vi.spyOn(api, 'novelty').mockRejectedValue(new Error('Your idea is too long'))
  renderPanel()
  fireEvent.change(idea(), { target: { value: 'Long idea' } })
  fireEvent.click(check())
  expect(await screen.findByText('Your idea is too long')).toBeInTheDocument()
})

test('the Library page opens the panel from a Has this been done? button', () => {
  render(<QueryClientProvider client={new QueryClient()}><LibraryPage /></QueryClientProvider>)
  expect(screen.queryByLabelText('Paste an idea or an abstract')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Has this been done?' }))
  expect(idea()).toBeInTheDocument()
})
