// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { SearchTab } from './SearchTab'
import { api } from '@/api/client'

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.spyOn(api, 'startSearchRun')
  vi.spyOn(api, 'getSearchRun')
  vi.spyOn(api, 'stopSearchRun')
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('renders the search controls', () => {
  renderWithClient(<SearchTab workspaceId="ws-1" />)
  expect(screen.getByLabelText('Search query')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument()
})

test('shows a status indicator once a run has started', async () => {
  const runningRun = {
    id: 'run-1',
    workspace_id: 'ws-1',
    query_text: 'code review LLM',
    filters_json: {},
    sources_json: ['arxiv'],
    status: 'running',
    started_at: '2026-09-24T00:00:00Z',
    stopped_at: null,
    stats_json: { last_batch_new_hits: 7 },
  } as never
  vi.mocked(api.startSearchRun).mockResolvedValue(runningRun)
  vi.mocked(api.getSearchRun).mockResolvedValue(runningRun)

  renderWithClient(<SearchTab workspaceId="ws-1" />)

  fireEvent.change(screen.getByLabelText('Search query'), { target: { value: 'code review LLM' } })
  fireEvent.click(screen.getByRole('button', { name: 'Start' }))

  await waitFor(() => expect(screen.getByText(/running/)).toBeInTheDocument())
  expect(screen.getByText(/7 new in last batch/)).toBeInTheDocument()
})

test('clicking Stop stops the in-progress run', async () => {
  const runningRunData = {
    id: 'run-1',
    workspace_id: 'ws-1',
    query_text: 'code review LLM',
    filters_json: {},
    sources_json: ['arxiv'],
    status: 'running',
    started_at: '2026-09-24T00:00:00Z',
    stopped_at: null,
    stats_json: {},
  }
  const stoppedRunData = { ...runningRunData, status: 'stopped', stopped_at: '2026-09-24T00:01:00Z' }
  vi.mocked(api.startSearchRun).mockResolvedValue(runningRunData as never)
  vi.mocked(api.getSearchRun).mockResolvedValue(runningRunData as never)
  vi.mocked(api.stopSearchRun).mockResolvedValue(stoppedRunData as never)

  renderWithClient(<SearchTab workspaceId="ws-1" />)

  fireEvent.change(screen.getByLabelText('Search query'), { target: { value: 'code review LLM' } })
  fireEvent.click(screen.getByRole('button', { name: 'Start' }))

  await waitFor(() => expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Stop' }))

  await waitFor(() => expect(api.stopSearchRun).toHaveBeenCalledWith('ws-1', 'run-1'))
})
