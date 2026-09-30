// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, test, vi } from 'vitest'
import { ReadingQueueTab } from './ReadingQueueTab'
import * as queries from '@/api/queries'

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

function mockQueue(data: { rows: object[] } | undefined) {
  vi.spyOn(queries, 'useReadingQueue').mockReturnValue({ data } as any)
}

afterEach(() => {
  vi.restoreAllMocks()
})

test('with no run selected, prompts to pick one on the Search tab instead of querying', () => {
  mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId={null} />)

  expect(queries.useReadingQueue).toHaveBeenCalledWith('ws-1', null, false)
  expect(screen.getByText(/pick a search run on the search tab/i)).toBeInTheDocument()
})

test('shows a loading message while the queue is being fetched', () => {
  mockQueue(undefined)
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(queries.useReadingQueue).toHaveBeenCalledWith('ws-1', 'run-1', true)
  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('shows an empty-state message when nothing included has been imported yet', () => {
  mockQueue({ rows: [] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(screen.getByText(/no included papers have been imported/i)).toBeInTheDocument()
})

test('renders a populated row with its title, priority, reading chip and note count', () => {
  mockQueue({ rows: [row] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  const link = screen.getByRole('link', { name: 'A Paper Worth Reading' })
  expect(link).toHaveAttribute('href', '#/papers/p1')
  expect(screen.getByText('Priority 2')).toBeInTheDocument()
  expect(screen.getByText('Pass 1 · Keep')).toBeInTheDocument()
  expect(screen.getByText('3 notes')).toBeInTheDocument()
})

test('a row with no priority and no reading progress shows plainly as not started, no blank cells', () => {
  mockQueue({ rows: [{ ...row, priority: null, reading_pass: 0, triage: null, note_count: 0 }] })
  renderWithClient(<ReadingQueueTab workspaceId="ws-1" runId="run-1" />)

  expect(screen.queryByText(/^Priority/)).not.toBeInTheDocument()
  expect(screen.getByText('Not started')).toBeInTheDocument()
  expect(screen.getByText('0 notes')).toBeInTheDocument()
})
