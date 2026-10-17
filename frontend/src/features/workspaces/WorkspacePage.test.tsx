// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { workspaceHref } from '@/lib/route'
import { WorkspacePage } from './WorkspacePage'

const counts = vi.hoisted(() => ({ paper_count: 1, note_count: 0 }))
const seen = vi.hoisted(() => ({ reading: null as unknown, papers: null as unknown }))
type Rows = { items: { stage2_status?: string | null }[] }
const hits = vi.hoisted(() => ({
  byKey: {} as Record<string, { rows: { stage2_status?: string | null }[]; more?: boolean }>,
}))
vi.mock('@/api/queries', () => ({
  useWorkspace: () => ({ data: { name: 'W', ...counts }, error: null }),
  useSearchHits: (_w: string, stage1?: string, acq?: string) => {
    const entry = hits.byKey[`${stage1 ?? ''}/${acq ?? ''}`] ?? { rows: [] }
    return { data: { pages: [{ items: entry.rows } as Rows] }, hasNextPage: !!entry.more }
  },
}))
vi.mock('@/components/AppShell', () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main>, shellTitle: () => null }))
vi.mock('./WorkspacePapers', () => ({
  WorkspacePapers: (props: { onTagsChange: (t: string[], m: 'any' | 'all') => void }) => {
    seen.papers = props
    return <button onClick={() => props.onTagsChange(['rct'], 'all')}>pick</button>
  },
}))
vi.mock('@/features/workspace-search/ManualAcquisitionTab', () => ({ ManualAcquisitionTab: () => null }))
vi.mock('@/features/workspace-search/PrismaTab', () => ({ PrismaTab: () => null }))
vi.mock('@/features/workspace-search/ReadingQueueTab', () => ({ ReadingQueueTab: (props: unknown) => { seen.reading = props; return null } }))
vi.mock('@/features/workspace-search/ScreeningTab', () => ({ ScreeningTab: () => null }))
vi.mock('@/features/workspace-search/SearchTab', () => ({ SearchTab: () => null }))
vi.mock('../evidence/EvidenceTab', () => ({ EvidenceTab: () => null }))
vi.mock('./WorkspaceChat', () => ({ WorkspaceChat: () => null }))
vi.mock('./WorkspaceNotes', () => ({ WorkspaceNotes: () => null }))
vi.mock('./ExportCitationsMenu', () => ({ ExportCitationsMenu: () => null }))

afterEach(() => {
  cleanup()
  seen.reading = null
  seen.papers = null
  hits.byKey = {}
  vi.unstubAllGlobals()
  counts.paper_count = 1
  counts.note_count = 0
})

test('a tag change keeps the active search run in the URL', () => {
  const replace = vi.fn()
  vi.stubGlobal('location', { ...window.location, replace })
  const run = '11111111-1111-4111-8111-111111111111'
  render(<WorkspacePage workspaceId="w1" tab="papers" runId={run} tags={[]} match="any" />)
  fireEvent.click(screen.getByText('pick'))
  expect(replace.mock.calls[0][0]).toContain(`run=${run}`)
})

const tabNames = () => screen.getAllByRole('tab').map((tab) => tab.getAttribute('aria-label') ?? tab.textContent)
const page = (tab: 'papers' | 'acquisition' | 'reading' = 'papers', runId: string | null = null) =>
  render(<WorkspacePage workspaceId="w1" tab={tab} runId={runId} tags={[]} match="any" />)

test('the tabs read as two labelled groups in the new order', () => {
  page()
  expect(screen.getByText('Your papers')).toBeTruthy()
  expect(screen.getByText('Systematic review')).toBeTruthy()
  expect(tabNames().map((name) => name.split(',')[0])).toEqual([
    'Papers', 'Notes', 'Chat', 'Evidence', 'Search & screen', 'Get PDFs', 'Full-text review', 'Reading list', 'PRISMA report',
  ])
  expect(screen.getByRole('tab', { name: /^Search & screen, step 1 of 5/ }).textContent).toContain('1 · Search & screen')
})

test('step tabs are named for their step', () => {
  page()
  expect(screen.getByRole('tab', { name: /^Get PDFs, step 2 of 5/ })).toBeTruthy()
})

test('a badge shows its count and hides at zero', () => {
  counts.paper_count = 146
  page()
  expect(screen.getByRole('tab', { name: 'Papers, 146 papers' })).toBeTruthy()
  expect(screen.getByRole('tab', { name: 'Notes' })).toBeTruthy()
})

test('the step line describes the active tab', () => {
  page('acquisition')
  expect(screen.getByText('Step 2 of 5. Relevant papers with no free PDF found. Get each one yourself and upload it.')).toBeTruthy()
})

test('a tab switch adds a history entry; a tag change replaces', () => {
  const assign = vi.fn()
  const replace = vi.fn()
  vi.stubGlobal('location', { ...window.location, assign, replace })
  page('papers', 'r1')
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Notes' }))
  expect(assign).toHaveBeenCalledWith(workspaceHref('w1', 'notes', 'r1'))
  fireEvent.click(screen.getByText('pick'))
  expect(replace).toHaveBeenCalledTimes(1)
})

test('old deep links still open their tab', () => {
  page('reading', 'r1')
  expect(screen.getByRole('tab', { name: 'Reading list, step 4 of 5' }).getAttribute('aria-selected')).toBe('true')
})

test('old deep links pass run, tags and match through unchanged', () => {
  render(<WorkspacePage workspaceId="w1" tab="reading" runId="r1" tags={['a']} match="all" />)
  expect(seen.reading).toMatchObject({ runId: 'r1' })
  expect(seen.papers).toMatchObject({ tags: ['a'], match: 'all' })
})

const rows = (n: number, stage2: (string | null)[] = []) =>
  Array.from({ length: n }, (_, i) => ({ stage2_status: stage2[i] ?? null }))

test('Get PDFs badge counts the failed hits', () => {
  hits.byKey['/failed'] = { rows: rows(3) }
  page()
  expect(screen.getByRole('tab', { name: 'Get PDFs, step 2 of 5, 3 to fetch' })).toBeTruthy()
})

test('Full-text review counts only hits without a stage-2 verdict', () => {
  hits.byKey['relevant/imported'] = { rows: rows(3, ['include', null, null]) }
  page()
  expect(screen.getByRole('tab', { name: 'Full-text review, step 3 of 5, 2 to review' })).toBeTruthy()
})

test('a count is omitted while more pages remain', () => {
  hits.byKey['/failed'] = { rows: rows(3), more: true }
  hits.byKey['relevant/manual'] = { rows: rows(2), more: true }
  page()
  expect(screen.getByRole('tab', { name: 'Get PDFs, step 2 of 5' })).toBeTruthy()
  expect(screen.getByRole('tab', { name: 'Full-text review, step 3 of 5' })).toBeTruthy()
})

test('a zero count shows no badge', () => {
  page()
  expect(screen.getByRole('tab', { name: 'Get PDFs, step 2 of 5' })).toBeTruthy()
  expect(screen.getByRole('tab', { name: 'Full-text review, step 3 of 5' })).toBeTruthy()
})
