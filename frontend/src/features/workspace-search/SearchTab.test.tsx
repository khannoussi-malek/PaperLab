// @vitest-environment jsdom
import { useState } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { SearchTab } from './SearchTab'
import { api } from '@/api/client'
import type { PaperSources } from '@/api/client'

/** `runId` is a prop from the URL in real life (WorkspacePage owns it) — this tiny stand-in plays that role for
 * tests that need to see a run actually start, so `onRunIdChange` has somewhere real to land. */
function Harness({ workspaceId }: { workspaceId: string }) {
  const [runId, setRunId] = useState<string | null>(null)
  return <SearchTab workspaceId={workspaceId} runId={runId} onRunIdChange={setRunId} />
}

const enabledSources: PaperSources = {
  contact_email: null,
  sources: [
    { id: 'arxiv', name: 'arXiv', enabled: true, has_key: null, key_hint: null },
    { id: 'crossref', name: 'Crossref', enabled: true, has_key: null, key_hint: null },
    { id: 'core', name: 'CORE', enabled: true, has_key: null, key_hint: null },
    { id: 'semantic_scholar', name: 'Semantic Scholar', enabled: true, has_key: null, key_hint: null },
    { id: 'openalex', name: 'OpenAlex', enabled: false, has_key: null, key_hint: null },
    { id: 'unpaywall', name: 'Unpaywall', enabled: true, has_key: null, key_hint: null },
  ],
}

function renderWithClient(ui: React.ReactElement, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) }
}

beforeEach(() => {
  vi.spyOn(api, 'startSearchRun')
  vi.spyOn(api, 'getSearchRun')
  vi.spyOn(api, 'stopSearchRun')
  vi.spyOn(api, 'paperSources').mockResolvedValue(enabledSources)
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('renders the search controls', () => {
  renderWithClient(<SearchTab workspaceId="ws-1" runId={null} onRunIdChange={vi.fn()} />)
  expect(screen.getByLabelText('Search query')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument()
})

test('shows a status indicator once a run has started, and reports the new run id (I1: for the URL, not local state)', async () => {
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

  renderWithClient(<Harness workspaceId="ws-1" />)

  fireEvent.change(screen.getByLabelText('Search query'), { target: { value: 'code review LLM' } })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Start' }))

  await waitFor(() => expect(api.getSearchRun).toHaveBeenCalledWith('ws-1', 'run-1'))
  await waitFor(() => expect(screen.getByText(/7 new in last batch/)).toBeInTheDocument())
})

test('a runId already set (as if restored from the URL on reload) shows the run at once, with no Start click', async () => {
  const runningRun = {
    id: 'run-1', workspace_id: 'ws-1', query_text: 'q', filters_json: {}, sources_json: ['arxiv'],
    status: 'running', started_at: '2026-09-24T00:00:00Z', stopped_at: null, stats_json: {},
  } as never
  vi.mocked(api.getSearchRun).mockResolvedValue(runningRun)

  renderWithClient(<SearchTab workspaceId="ws-1" runId="run-1" onRunIdChange={vi.fn()} />)

  await waitFor(() => expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument())
  expect(api.getSearchRun).toHaveBeenCalledWith('ws-1', 'run-1')
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

  renderWithClient(<Harness workspaceId="ws-1" />)

  fireEvent.change(screen.getByLabelText('Search query'), { target: { value: 'code review LLM' } })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Start' }))

  await waitFor(() => expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument())
  fireEvent.click(screen.getByRole('button', { name: 'Stop' }))

  await waitFor(() => expect(api.stopSearchRun).toHaveBeenCalledWith('ws-1', 'run-1'))
})

test('a 409 from Stop (the run already finished naturally) is swallowed, not shown as an error (Minor 5)', async () => {
  const runningRun = {
    id: 'run-1', workspace_id: 'ws-1', query_text: 'q', filters_json: {}, sources_json: ['arxiv'],
    status: 'running', started_at: '2026-09-24T00:00:00Z', stopped_at: null, stats_json: {},
  }
  const exhaustedRun = { ...runningRun, status: 'exhausted', stopped_at: '2026-09-24T00:01:00Z' }
  vi.mocked(api.getSearchRun).mockResolvedValue(runningRun as never)
  vi.mocked(api.stopSearchRun).mockRejectedValue(new Error('search_run_not_running'))

  renderWithClient(<SearchTab workspaceId="ws-1" runId="run-1" onRunIdChange={vi.fn()} />)

  await waitFor(() => expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument())
  vi.mocked(api.getSearchRun).mockResolvedValue(exhaustedRun as never) // what a real Stop-race would actually find
  fireEvent.click(screen.getByRole('button', { name: 'Stop' }))

  // The mutation resolves (via a re-fetch of the run) instead of erroring, so the UI catches up to "exhausted"
  // and no alert ever appears.
  await waitFor(() => expect(screen.getByText(/exhausted/)).toBeInTheDocument())
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('invalidates the hit pool on each real batch, keyed on cumulative raw counts (not last_batch_new_hits) plus status (I1 fix round)', async () => {
  const runKey = { queryKey: ['workspaces', 'ws-1', 'search', 'runs', 'run-1'] }
  const hitsKey = { queryKey: ['workspaces', 'ws-1', 'search', 'hits'] }
  // last_batch_new_hits deliberately repeats 20 across every tick below, including two genuinely different real
  // batches — the bug this round fixed treated a repeated last_batch_new_hits as "nothing new," even though the
  // cumulative per_source_raw_count total (workers/workspace_search.py's own running total) kept growing.
  const runAt = (arxivRawCount: number, status = 'running') => ({
    id: 'run-1', workspace_id: 'ws-1', query_text: 'q', filters_json: {}, sources_json: ['arxiv'],
    status, started_at: '2026-09-24T00:00:00Z', stopped_at: null,
    stats_json: { last_batch_new_hits: 20, per_source_raw_count: { arxiv: arxivRawCount } },
  })
  vi.mocked(api.getSearchRun).mockResolvedValue(runAt(20) as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries')

  renderWithClient(<SearchTab workspaceId="ws-1" runId="run-1" onRunIdChange={vi.fn()} />, client)

  await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith(hitsKey))
  const callsAfterFirstBatch = invalidateSpy.mock.calls.length

  // A second, genuinely different batch that happens to report the same last_batch_new_hits (20) as the first
  // must still invalidate, since the cumulative raw-count total grew (20 -> 40) — this is the case the old
  // last_batch_new_hits-only key missed, including on a run's very last batch.
  vi.mocked(api.getSearchRun).mockResolvedValue(runAt(40) as never)
  await client.refetchQueries(runKey)
  await waitFor(() => expect(invalidateSpy.mock.calls.length).toBeGreaterThan(callsAfterFirstBatch))
  const callsAfterSecondBatch = invalidateSpy.mock.calls.length

  // A poll tick reporting the exact same state as last time (nothing new at all) must not invalidate again.
  vi.mocked(api.getSearchRun).mockResolvedValue(runAt(40) as never)
  await client.refetchQueries(runKey)
  await waitFor(() => expect(api.getSearchRun).toHaveBeenCalledTimes(3)) // lets the resulting render/effect flush
  expect(invalidateSpy.mock.calls.length).toBe(callsAfterSecondBatch)

  // The run's transition to a terminal status forces one final invalidation, even though the raw-count sum is
  // unchanged from the tick just before it (e.g. the terminal-marking pass itself added nothing new) — otherwise
  // a last batch that happened to repeat the previous total would never reach the pool.
  vi.mocked(api.getSearchRun).mockResolvedValue(runAt(40, 'exhausted') as never)
  await client.refetchQueries(runKey)
  await waitFor(() => expect(invalidateSpy.mock.calls.length).toBeGreaterThan(callsAfterSecondBatch))
})
