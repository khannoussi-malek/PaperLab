// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import type { Paper } from '@/api/client'
import { PaperList } from '@/features/library/PaperList'
import { WorkspacePapers } from './WorkspacePapers'
import { tagSummary } from './tagFixtures'

vi.mock('@/features/library/PaperPreview', () => ({ PaperPreview: () => null })) // pulls in pdfjs, which needs a worker
vi.stubGlobal('matchMedia', () => ({ matches: false }))
vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
Element.prototype.scrollIntoView = () => {}

const paper = (id: string, title: string) => ({
  id, title, authors: [], year: null, venue: null, page_count: null, status: 'ready', status_error: null,
  peer_reviewed: 'unknown', evidence_access: 'metadata', source_type: null, is_retracted: false,
}) as unknown as Paper

const papers = [paper('p1', 'Alpha trial'), paper('p2', 'Beta cohort'), paper('p3', 'Gamma study')]
const map = { p1: ['rct', 'cohort'], p2: ['cohort'], p3: [] as string[] }

function setup(tags: string[], match: 'any' | 'all' = 'any', data: Paper[] | null = papers) {
  vi.spyOn(queries, 'useWorkspacePapers').mockReturnValue({ data: data ?? undefined } as any)
  vi.spyOn(queries, 'useTags').mockReturnValue({ data: [tagSummary('rct', 1), tagSummary('cohort', 2)] } as any)
  vi.spyOn(queries, 'usePaperTags').mockReturnValue({ data: map } as any)
  vi.spyOn(queries, 'useApplyTag').mockReturnValue({ mutate: vi.fn(), error: null } as any)
  vi.spyOn(queries, 'useRemoveTag').mockReturnValue({ mutate: vi.fn(), error: null } as any)
  vi.spyOn(queries, 'useRenameTag').mockReturnValue({ mutate: vi.fn(), reset: vi.fn() } as any)
  vi.spyOn(queries, 'useDeleteTag').mockReturnValue({ mutate: vi.fn(), reset: vi.fn() } as any)
  const onTagsChange = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <WorkspacePapers workspaceId="w1" tags={tags} match={match} onTagsChange={onTagsChange} />
    </QueryClientProvider>,
  )
  return onTagsChange
}

afterEach(() => { localStorage.clear(); cleanup(); vi.restoreAllMocks() })

const rows = () => Array.from(document.querySelectorAll('li.paper-row')).map((r) => r.querySelector('a')?.textContent)

test('chips sit in each row and clicking one adds the tag to the filter', () => {
  const onTagsChange = setup(['cohort'])
  const chips = screen.getAllByRole('button', { name: 'Filter by tag rct' })
  expect(chips).toHaveLength(1)
  expect(chips[0].closest('li')?.querySelector('a')?.contains(chips[0])).toBe(false)
  fireEvent.click(chips[0])
  expect(onTagsChange).toHaveBeenCalledWith(['cohort', 'rct'], 'any')
})

test('a chip of a filtered tag is pressed and does nothing more', () => {
  const onTagsChange = setup(['cohort'])
  const chips = screen.getAllByRole('button', { name: 'Filter by tag cohort' })
  expect(chips.every((c) => c.getAttribute('aria-pressed') === 'true')).toBe(true)
  expect(screen.getByRole('button', { name: 'Filter by tag rct' }).getAttribute('aria-pressed')).toBe('false')
  fireEvent.click(chips[0])
  expect(onTagsChange).not.toHaveBeenCalled()
})

test('while tags are loading the list is unfiltered', () => {
  vi.spyOn(queries, 'useWorkspacePapers').mockReturnValue({ data: papers } as any)
  vi.spyOn(queries, 'useTags').mockReturnValue({ data: [tagSummary('rct', 1)] } as any)
  vi.spyOn(queries, 'usePaperTags').mockReturnValue({ data: undefined } as any)
  const client = new QueryClient()
  render(<QueryClientProvider client={client}><WorkspacePapers workspaceId="w1" tags={['rct']} match="all" onTagsChange={vi.fn()} /></QueryClientProvider>)
  expect(rows()).toHaveLength(3)
  expect(screen.queryByText(/No papers carry/)).toBeNull()
})

test('an empty filter result keeps the search text', () => {
  const onTagsChange = vi.fn()
  vi.spyOn(queries, 'useWorkspacePapers').mockReturnValue({ data: papers } as any)
  vi.spyOn(queries, 'useTags').mockReturnValue({ data: [tagSummary('rct', 1), tagSummary('cohort', 2)] } as any)
  vi.spyOn(queries, 'usePaperTags').mockReturnValue({ data: { p1: ['rct'], p2: ['cohort'], p3: [] } } as any)
  const client = new QueryClient()
  const view = (match: 'any' | 'all') => (
    <QueryClientProvider client={client}><WorkspacePapers workspaceId="w1" tags={['rct', 'cohort']} match={match} onTagsChange={onTagsChange} /></QueryClientProvider>
  )
  const { rerender } = render(view('any'))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'alpha' } })
  rerender(view('all'))
  expect(screen.getByText('No papers carry all of those tags.')).toBeTruthy()
  rerender(view('any'))
  expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('alpha')
  expect(rows()).toEqual(['Alpha trial'])
})

test('any shows papers with either tag, all only those with both', () => {
  setup(['rct', 'cohort'])
  expect(rows()).toEqual(['Alpha trial', 'Beta cohort'])
  cleanup()
  setup(['rct', 'cohort'], 'all')
  expect(rows()).toEqual(['Alpha trial'])
})

test('a tag that does not exist is ignored', () => {
  setup(['ghost'])
  expect(rows()).toHaveLength(3)
})

test('renders both the wide sidebar and the narrow dropdown', () => {
  setup([])
  expect(document.querySelector('aside.hidden.lg\\:block')).not.toBeNull()
  expect(document.querySelector('.lg\\:hidden')).not.toBeNull()
})

test('the Library list has no chips and no checkboxes', () => {
  const client = new QueryClient()
  render(<QueryClientProvider client={client}><PaperList papers={papers} /></QueryClientProvider>)
  expect(screen.queryByRole('button', { name: /Filter by tag/ })).toBeNull()
  expect(screen.queryByRole('checkbox')).toBeNull()
})

test('selecting rows shows the bar, Clear empties it, and the bar is absent with nothing selected', () => {
  setup([])
  expect(screen.queryByText(/selected$/)).toBeNull()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select Alpha trial' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select Beta cohort' }))
  expect(screen.getByText('2 selected')).toBeTruthy()
  expect(screen.getByText('2 selected').getAttribute('role')).toBe('status')
  expect(screen.getByRole('button', { name: 'Tag…' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Remove tag…' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
  expect(screen.queryByText(/selected$/)).toBeNull()
})

test('a filter change that hides a selected paper drops it from the selection', () => {
  const onTagsChange = vi.fn()
  const client = new QueryClient()
  setup([])
  const view = (tags: string[]) => (
    <QueryClientProvider client={client}><WorkspacePapers workspaceId="w1" tags={tags} match="any" onTagsChange={onTagsChange} /></QueryClientProvider>
  )
  cleanup()
  const { rerender } = render(view([]))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select Alpha trial' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select Gamma study' }))
  expect(screen.getByText('2 selected')).toBeTruthy()
  rerender(view(['cohort']))
  expect(screen.getByText('1 selected')).toBeTruthy()
})

test('papers hidden by the list\'s own search are no longer selected, counted or tagged', () => {
  const apply = vi.fn()
  setup([])
  vi.spyOn(queries, 'useApplyTag').mockReturnValue({ mutate: apply, error: null, reset: vi.fn() } as any)
  cleanup()
  const client = new QueryClient()
  render(<QueryClientProvider client={client}><WorkspacePapers workspaceId="w1" tags={[]} match="any" onTagsChange={vi.fn()} /></QueryClientProvider>)
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select Alpha trial' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Select Beta cohort' }))
  expect(screen.getByText('2 selected')).toBeTruthy()
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search papers' }), { target: { value: 'Alpha' } })
  expect(screen.getByText('1 selected')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Tag…' }))
  fireEvent.click(screen.getByRole('option', { name: /rct/ }))
  expect(apply).toHaveBeenCalledWith({ tag: 'rct', paperIds: ['p1'] }, expect.anything())
})

test('while loading it shows a skeleton, not the empty copy', () => {
  setup([], 'any', null)
  expect(screen.getByText('Loading papers').closest('[role="status"]')).toHaveAttribute('aria-busy', 'true')
  expect(screen.queryByText('No papers yet')).toBeNull()
})

test('an empty workspace says so and keeps the three add buttons', () => {
  setup([], 'any', [])
  expect(screen.getByRole('heading', { name: 'No papers yet' })).toBeTruthy()
  expect(screen.getByText('Add them from your library, upload PDFs, or find one by DOI or title.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Add from library' })).toBeTruthy()
})

test('"Find by DOI or title" on the Papers tab opens the find dialog', () => {
  setup([])
  fireEvent.click(screen.getByRole('button', { name: 'Find by DOI or title' }))
  expect(screen.getByRole('dialog', { name: 'Find papers' })).toBeTruthy()
})

test('the three ways in are named in words', () => {
  setup([])
  const ways = [
    ['Add from library', 'Pick papers already in your library.'],
    ['Upload PDFs', 'Add PDFs from your computer.'],
    ['Find by DOI or title', 'Look a paper up by DOI, arXiv ID or title.'],
  ]
  for (const [name, tip] of ways) {
    const button = screen.getByRole('button', { name })
    act(() => button.focus())
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent(tip)
    expect(button.getAttribute('aria-describedby')).toBe(screen.getByText(tip, { selector: '[data-slot=tooltip-content]' }).id)
    act(() => button.blur())
  }
  expect(screen.queryByRole('button', { name: /Add papers|Find papers/ })).toBeNull()
})

test('a paper without a PDF is badged in its row, with no pages flying and no status chip while its abstract embeds', () => {
  const pdfLess = { ...paper('p4', 'Delta abstract'), status: 'embedding', has_pdf: false } as Paper
  setup([], 'any', [pdfLess])
  const row = document.querySelector('li.paper-row')!
  expect(row).toHaveTextContent('No PDF yet')
  expect(row.querySelector('.embedding-page')).toBeNull()
  expect(row.querySelector('.status')).toHaveClass('sr-only')
})

test('the Deck view drops checkboxes and the selection bar; List brings them back with the pick kept', () => {
  setup([])
  fireEvent.click(screen.getAllByRole('checkbox')[0])
  expect(screen.getByText('1 selected')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Deck' }))
  expect(localStorage.getItem('paperlab-workspace-papers-view')).toBe('deck')
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.queryByText('1 selected')).toBeNull()
  expect(screen.queryByRole('button', { name: /Remove from workspace/ })).toBeNull()
  expect(screen.getByRole('group', { name: 'Show papers as' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Paper actions' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'List' }))
  expect(screen.getAllByRole('button', { name: 'Paper actions' }).length).toBeGreaterThan(0)
  expect(screen.getByText('1 selected')).toBeInTheDocument()
})
