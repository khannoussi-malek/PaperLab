// @vitest-environment jsdom
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, test, vi } from 'vitest'
import { ReadingQueueTab } from './ReadingQueueTab'
import * as queries from '@/api/queries'
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
  identified: 0,
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
}

function mockRuns(data: PrismaExportOut | undefined, isPending = false) {
  vi.spyOn(queries, 'usePrismaExport').mockReturnValue({ data, isPending } as any)
}

function mockQueue(data: { rows: object[] } | undefined, extra: Partial<ReturnType<typeof queries.useReadingQueue>> = {}) {
  const spy = vi.spyOn(queries, 'useReadingQueue').mockReturnValue({ data, isError: false, error: null, ...extra } as any)
  return spy
}

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

test('defaults the picker to the runId prop when one is given', () => {
  mockRuns(runsData)
  const spy = mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(spy).toHaveBeenCalledWith('ws-1', 'run-1', true)
  expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('run-1')
})

test('with no runId prop, defaults the picker to the most recently started run', () => {
  mockRuns(runsData)
  const spy = mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId={null} />)

  expect(spy).toHaveBeenCalledWith('ws-1', 'run-2', true)
  expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('run-2')
})

test('picking a different run from the dropdown re-queries the reading queue for it', () => {
  mockRuns(runsData)
  const spy = mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-2" />)

  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'run-1' } })

  expect(spy).toHaveBeenCalledWith('ws-1', 'run-1', true)
})

test('shows a loading message while the queue itself is being fetched', () => {
  mockRuns(runsData)
  mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(screen.getAllByText(/loading/i).length).toBeGreaterThan(0)
})

test('shows an alert with the error message when the queue request fails', () => {
  mockRuns(runsData)
  mockQueue(undefined, { isError: true, error: new Error('Could not load the reading queue.') })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(screen.getByRole('alert')).toHaveTextContent('Could not load the reading queue.')
})

test('shows an empty-state message when nothing included has been imported yet', () => {
  mockRuns(runsData)
  mockQueue({ rows: [] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(screen.getByText(/no included papers have been imported/i)).toBeInTheDocument()
})

test('renders a populated row with its title, priority, reading chip and note count', () => {
  mockRuns(runsData)
  mockQueue({ rows: [row] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  const link = screen.getByRole('link', { name: 'A Paper Worth Reading' })
  expect(link).toHaveAttribute('href', '#/papers/p1')
  expect(screen.getByText('Priority 2')).toBeInTheDocument()
  expect(screen.getByText('Pass 1 · Keep')).toBeInTheDocument()
  expect(screen.getByText('3 notes')).toBeInTheDocument()
})

test('singularizes the note count for exactly one note', () => {
  mockRuns(runsData)
  mockQueue({ rows: [{ ...row, note_count: 1 }] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(screen.getByText('1 note')).toBeInTheDocument()
})

test('a row with no priority and no reading progress shows plainly as not started, no blank cells', () => {
  mockRuns(runsData)
  mockQueue({ rows: [{ ...row, priority: null, reading_pass: 0, triage: null, note_count: 0 }] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(screen.queryByText(/^Priority/)).not.toBeInTheDocument()
  expect(screen.getByText('Not started')).toBeInTheDocument()
  expect(screen.getByText('0 notes')).toBeInTheDocument()
})
