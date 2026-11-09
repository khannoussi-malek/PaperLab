// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ReadingQueueTab } from './ReadingQueueTab'
import { api } from '@/api/client'
import * as queries from '@/api/queries'
import * as stepCounts from '@/features/workspaces/useStepCounts'
import type { PrismaExportOut } from '@/api/client'

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const row = {
  paper_id: 'p1',
  title: 'A Paper Worth Reading',
  priority: 2,
  reading_pass: 1,
  triage: 'keep',
  note_count: 3,
}

// Two past runs, like PrismaTab.test.tsx's own fixture — 'run-2' is the more recently started one, so it's the
// default pick whenever no `runId` prop and no manual selection point elsewhere. The funnel counts are irrelevant
// here (ReadingQueueTab only reads `.runs`) but PrismaExportOut requires them.
const runsData: PrismaExportOut = {
  identified: 0, sources_searched: [], sources_not_searched: [], citation_searching: [], identified_databases: 0,
  duplicates_removed: 0,
  stage1_screened: 0,
  stage1_excluded: 0,
  stage1_excluded_by_reason: {},
  sought: 0,
  not_retrieved: 0,
  stage2_assessed: 0,
  stage2_excluded: 0,
  stage2_excluded_by_reason: {},
  included: 0,
  runs: [
    { id: 'run-1', query_text: 'transformer efficiency', filters_json: {}, started_at: '2026-09-24T00:00:00Z' },
    { id: 'run-2', query_text: 'llm evaluation', filters_json: {}, started_at: '2026-09-24T00:05:00Z' },
  ],
  automation: [],
  screening_criteria: null,
  notes: [],
}

function mockRuns(data: PrismaExportOut | undefined, isPending = false) {
  vi.spyOn(queries, 'usePrismaExport').mockReturnValue({ data, isPending } as any)
}

function mockQueue(data: { rows: object[] } | undefined, extra: Partial<ReturnType<typeof queries.useReadingQueue>> = {}) {
  const spy = vi.spyOn(queries, 'useReadingQueue').mockReturnValue({ data, isError: false, error: null, ...extra } as any)
  return spy
}

// Every run has included papers unless a test says otherwise (the default-run probes go through api.readingQueue).
beforeEach(() => {
  vi.spyOn(stepCounts, 'useStepCounts').mockReturnValue({})
  vi.spyOn(api, 'readingQueue').mockResolvedValue({ rows: [row] } as any)
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('shows a loading message while the workspace run list is being fetched', () => {
  mockRuns(undefined, true)
  mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId={null} />)

  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('with no runs in the workspace yet, prompts to start one on the Search tab instead of showing a picker', () => {
  mockRuns({ ...runsData, runs: [] })
  mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId={null} />)

  expect(screen.getByText(/no search runs yet/i)).toBeInTheDocument()
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
})

test('defaults the picker to All runs, whatever runId prop is given', async () => {
  mockRuns(runsData)
  const spy = mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  await waitFor(() => expect(spy).toHaveBeenCalledWith('ws-1', 'all'))
  expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('all')
  expect(screen.getByRole('option', { name: 'All runs' })).toBeInTheDocument()
})

test('All runs lists the included papers of several runs; picking a run filters to it', async () => {
  mockRuns(runsData)
  vi.spyOn(api, 'readingQueue').mockImplementation(async (_ws: string, id: string) => ({
    rows: id === 'run-1' ? [row] : id === 'run-2' ? [{ ...row, paper_id: 'p2', title: 'Second' }] : [row, { ...row, paper_id: 'p2', title: 'Second' }],
  }) as any)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId={null} />)

  expect(await screen.findByRole('link', { name: 'A Paper Worth Reading' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Second' })).toBeInTheDocument()

  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'run-2' } })
  await waitFor(() => expect(screen.queryByRole('link', { name: 'A Paper Worth Reading' })).not.toBeInTheDocument())
  expect(await screen.findByRole('link', { name: 'Second' })).toBeInTheDocument()
})

test('picking a different run from the dropdown re-queries the reading queue for it', async () => {
  mockRuns(runsData)
  const spy = mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-2" />)
  await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument())

  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'run-1' } })

  expect(spy).toHaveBeenCalledWith('ws-1', 'run-1')
})

test('shows a loading message while the queue itself is being fetched', () => {
  mockRuns(runsData)
  mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(screen.getAllByText(/loading/i).length).toBeGreaterThan(0)
})

test('shows the error and a Retry that refetches when the queue request fails', async () => {
  const refetch = vi.fn()
  mockRuns(runsData)
  mockQueue(undefined, { isError: true, error: new Error('Could not load the reading queue.'), refetch })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)
  await screen.findByRole('combobox')

  expect(screen.getByRole('alert')).toHaveTextContent('Could not load the reading queue.')
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(refetch).toHaveBeenCalled()
})

test('with nothing included and nothing waiting, the empty state says how to fill the list and has no button', async () => {
  mockRuns(runsData)
  mockQueue({ rows: [] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)
  await screen.findByRole('combobox')

  expect(screen.getByRole('heading', { name: 'Nothing to read yet' })).toBeInTheDocument()
  expect(screen.getByText('Papers you include in Full-text review appear here, in reading order.')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Full-text review/ })).not.toBeInTheDocument()
})

test('with papers waiting for full-text review, the empty state links to that tab with the count', async () => {
  vi.spyOn(stepCounts, 'useStepCounts').mockReturnValue({ screening: 6 })
  mockRuns(runsData)
  mockQueue({ rows: [] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId={null} />)
  await screen.findByRole('combobox')

  expect(screen.getByRole('link', { name: 'Go to Full-text review (6 waiting)' })).toHaveAttribute('href', expect.stringContaining('tab=screening'))
})

test('renders a populated row with its title, priority, reading chip and note count', async () => {
  mockRuns(runsData)
  mockQueue({ rows: [row] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)
  await screen.findByRole('combobox')

  const link = screen.getByRole('link', { name: 'A Paper Worth Reading' })
  expect(link).toHaveAttribute('href', '#/papers/p1')
  expect(screen.getByText('Priority 2')).toBeInTheDocument()
  expect(screen.getByText('Pass 1 · Keep')).toBeInTheDocument()
  expect(screen.getByText('3 notes')).toBeInTheDocument()
})

test('singularizes the note count for exactly one note', async () => {
  mockRuns(runsData)
  mockQueue({ rows: [{ ...row, note_count: 1 }] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)
  await screen.findByRole('combobox')

  expect(screen.getByText('1 note')).toBeInTheDocument()
})

test('a row with no priority and no reading progress shows plainly as not started, no blank cells', async () => {
  mockRuns(runsData)
  mockQueue({ rows: [{ ...row, priority: null, reading_pass: 0, triage: null, note_count: 0 }] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)
  await screen.findByRole('combobox')

  expect(screen.queryByText(/^Priority/)).not.toBeInTheDocument()
  expect(screen.getByText('Not started')).toBeInTheDocument()
  expect(screen.getByText('0 notes')).toBeInTheDocument()
})

test('while loading it shows a skeleton, not the empty copy', () => {
  mockRuns(runsData)
  mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)
  expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
  expect(screen.queryByText('Nothing to read yet')).not.toBeInTheDocument()
})

test('a failed runs query shows the error and Retry, not "No search runs yet"', () => {
  const refetch = vi.fn()
  vi.spyOn(queries, 'usePrismaExport').mockReturnValue({ data: undefined, isPending: false, isError: true, error: new Error('Nope.'), refetch } as any)
  mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId={null} />)
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(refetch).toHaveBeenCalled()
  expect(screen.queryByText('No search runs yet')).not.toBeInTheDocument()
})

test('with no runs it says so and links to step 1', () => {
  mockRuns({ ...runsData, runs: [] })
  mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId={null} />)
  expect(screen.getByRole('heading', { name: 'No search runs yet' })).toBeInTheDocument()
  expect(screen.getByText('Start one on 1 · Search & screen.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Go to 1 · Search & screen' })).toBeInTheDocument()
})

test('explains which papers count', async () => {
  mockRuns(runsData)
  mockQueue({ rows: [row] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)
  await screen.findByRole('combobox')
  expect(screen.getByText("Only papers you included in step 3 appear here. Papers added on the Papers tab aren't part of the review flow.")).toBeInTheDocument()
})

test('a row whose paper has no PDF carries the "No PDF yet" badge', async () => {
  vi.spyOn(api, 'listWorkspacePapers').mockResolvedValue([{ id: 'p1', has_pdf: false }, { id: 'p2', has_pdf: true }] as any)
  mockRuns(runsData)
  mockQueue({ rows: [row, { ...row, paper_id: 'p2', title: 'Has a file' }] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId={null} />)

  const noPdf = await screen.findAllByText('No PDF yet')
  expect(noPdf).toHaveLength(1)
  expect(noPdf[0].closest('li')).toHaveTextContent('A Paper Worth Reading')
})
