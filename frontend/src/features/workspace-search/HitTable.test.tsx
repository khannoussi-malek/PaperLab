// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { HitTable } from './HitTable'
import { api, type Hit } from '@/api/client'

/** The row list only — excludes the preview panel, which also renders the current hit's title/byline. Always
 * present (even before data loads), so this can be synchronous. */
const pool = () => within(screen.getByLabelText('Hit pool'))
/** The preview panel only. Only mounts once there's a hit to preview, so this is async. */
const preview = async () => within(await screen.findByLabelText('Hit preview'))

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) }
}

const baseHit = {
  id: 'h1',
  run_id: 'run-1',
  external_ref_id: null,
  source_method: 'arxiv',
  normalized_title: 'a paper about llms',
  first_seen_at: '2026-09-24T00:00:00Z',
  stage1_status: null,
  stage1_exclude_reason: null,
  stage1_note: null,
  priority: null,
  topic_fit: null,
  acquisition_status: 'pending',
  paper_id: null,
} satisfies Hit

beforeEach(() => {
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: [baseHit], next_cursor: null })
  vi.spyOn(api, 'patchSearchHit').mockResolvedValue(baseHit)
  vi.spyOn(api, 'importSearchHits')
  vi.spyOn(api, 'uploadHitPdf')
  // jsdom never lays anything out, so offsetHeight is always 0 — the virtualizer treats a zero-height
  // scroll container as "nothing visible" and renders no rows at all. Give it a plausible viewport.
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(600)
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(600)
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('renders hit titles from the paginated query', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  expect(await pool().findByText('a paper about llms')).toBeInTheDocument()
})

test('a hit with a linked ExternalRef shows its real title and a compact byline in the row, not just normalized_title', async () => {
  const richHit: Hit = {
    ...baseHit,
    title: 'Attention Is All You Need',
    authors: ['Ashish Vaswani', 'Noam Shazeer', 'Niki Parmar', 'Jakob Uszkoreit'],
    year: 2017,
  }
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: [richHit], next_cursor: null })

  renderWithClient(<HitTable workspaceId="ws-1" />)
  await pool().findByText(/Attention Is All You Need/)

  // Byline caps at 3 authors even though 4 are present.
  expect(pool().getByText(/Ashish Vaswani, Noam Shazeer, Niki Parmar · 2017/)).toBeInTheDocument()
  expect(pool().queryByText(/Jakob Uszkoreit/)).not.toBeInTheDocument()
  expect(pool().queryByText('a paper about llms')).not.toBeInTheDocument()
})

test('hovering a row previews its title, byline and abstract in the side panel', async () => {
  const richHit: Hit = {
    ...baseHit,
    title: 'Attention Is All You Need',
    authors: ['Ashish Vaswani'],
    year: 2017,
    venue: 'NeurIPS',
    abstract: 'The dominant sequence transduction models are based on complex recurrent networks.',
  }
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: [richHit], next_cursor: null })

  renderWithClient(<HitTable workspaceId="ws-1" />)
  // A single hit is previewed by default (falls back to the first loaded row) — no hover needed to see it here.
  const panel = await preview()
  await panel.findByText('Attention Is All You Need')

  expect(panel.getByText('Ashish Vaswani · 2017 · NeurIPS')).toBeInTheDocument()
  expect(
    panel.getByText('The dominant sequence transduction models are based on complex recurrent networks.'),
  ).toBeInTheDocument()
})

test('a hit with no linked ExternalRef previews its normalized title and says no abstract is available', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)

  const panel = await preview()
  expect(await panel.findByText('a paper about llms')).toBeInTheDocument()
  expect(panel.getByText('No abstract available for this hit.')).toBeInTheDocument()
})

test('focusing a different row (via its ⋮ button) swaps the preview immediately, no hover delay', async () => {
  const hits: Hit[] = [
    { ...baseHit, id: 'h1', title: 'First Paper', normalized_title: 'first paper' },
    { ...baseHit, id: 'h2', title: 'Second Paper', normalized_title: 'second paper' },
  ]
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: hits, next_cursor: null })

  renderWithClient(<HitTable workspaceId="ws-1" />)
  const panel = await preview()
  await panel.findByText('First Paper') // the first row previews by default

  const [, secondRowMenuButton] = pool().getAllByRole('button', { name: 'Hit actions' })
  fireEvent.focus(secondRowMenuButton)

  await panel.findByText('Second Paper')
  expect(panel.queryByText('First Paper')).not.toBeInTheDocument()
})

test('the preview panel offers the same review actions as the menu, so reading and deciding are the same step', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  const panel = await preview()
  await panel.findByText('a paper about llms')

  fireEvent.click(panel.getByRole('button', { name: 'Relevant' }))

  await waitFor(() => expect(api.patchSearchHit).toHaveBeenCalledWith('ws-1', 'h1', { stage1_status: 'relevant' }))
})

test('the preview panel requires a reason before Not relevant can be clicked, same rule as the menu', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  const panel = await preview()
  await panel.findByText('a paper about llms')

  expect(panel.getByRole('button', { name: 'Not relevant' })).toBeDisabled()

  fireEvent.change(panel.getByLabelText('Exclusion reason'), { target: { value: 'duplicate' } })
  expect(panel.getByRole('button', { name: 'Not relevant' })).toBeEnabled()
  fireEvent.click(panel.getByRole('button', { name: 'Not relevant' }))

  await waitFor(() =>
    expect(api.patchSearchHit).toHaveBeenCalledWith('ws-1', 'h1', {
      stage1_status: 'not_relevant',
      stage1_exclude_reason: 'duplicate',
    }),
  )
})

test('the preview panel offers a way to get the PDF for a hit that needs one: search, open page, copy DOI, upload', async () => {
  const hit: Hit = { ...baseHit, doi: '10.1234/attention', acquisition_status: 'failed' }
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: [hit], next_cursor: null })

  renderWithClient(<HitTable workspaceId="ws-1" />)
  const panel = await preview()
  await panel.findByText('a paper about llms')

  expect(panel.getByRole('button', { name: 'Add PDF' })).toBeInTheDocument()
  expect(panel.getByRole('link', { name: 'Search by title' })).toHaveAttribute(
    'href',
    'https://scholar.google.com/scholar?q=a%20paper%20about%20llms',
  )
  expect(panel.getByRole('link', { name: 'Open page' })).toHaveAttribute('href', 'https://doi.org/10.1234/attention')
  expect(panel.getByRole('button', { name: 'Copy DOI' })).toBeInTheDocument()
  expect(panel.getByLabelText('Upload PDF for a paper about llms')).toBeInTheDocument()
})

test('clicking "Add PDF" in the preview panel imports only that one hit, not the whole filter, and never re-fetches the pool', async () => {
  const hit: Hit = { ...baseHit, acquisition_status: 'pending' }
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: [hit], next_cursor: null })
  vi.spyOn(api, 'importSearchHits').mockResolvedValue({ imported: 1, failed: 0 })

  renderWithClient(<HitTable workspaceId="ws-1" />)
  const panel = await preview()
  await panel.findByText('a paper about llms')
  const callsBeforeClick = vi.mocked(api.listSearchHits).mock.calls.length

  fireEvent.click(panel.getByRole('button', { name: 'Add PDF' }))

  await waitFor(() => expect(api.importSearchHits).toHaveBeenCalledWith('ws-1', ['h1']))
  // A successful import updates the hit's own acquisition_status (the "Get the PDF" section disappears)
  // by patching the already-loaded row in place, not by re-fetching the pool from the server.
  await waitFor(() => expect(panel.queryByRole('button', { name: 'Add PDF' })).not.toBeInTheDocument())
  expect(api.listSearchHits).toHaveBeenCalledTimes(callsBeforeClick)
})

test('a hit with no free PDF found stays acquirable and tells the user to use the manual options', async () => {
  const hit: Hit = { ...baseHit, acquisition_status: 'pending' }
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: [hit], next_cursor: null })
  vi.spyOn(api, 'importSearchHits').mockResolvedValue({ imported: 0, failed: 1 })

  renderWithClient(<HitTable workspaceId="ws-1" />)
  const panel = await preview()
  await panel.findByText('a paper about llms')

  fireEvent.click(panel.getByRole('button', { name: 'Add PDF' }))

  expect(await screen.findByRole('status')).toHaveTextContent('No PDF found automatically')
  // Not a mutation error — the manual fallback options stay offered, same as any other unacquired hit.
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(panel.getByRole('link', { name: 'Search by title' })).toBeInTheDocument()
})

test('uploading a PDF from the preview panel calls the upload mutation for that hit', async () => {
  vi.spyOn(api, 'uploadHitPdf').mockResolvedValue({ ...baseHit, acquisition_status: 'manual', paper_id: 'p1' })
  renderWithClient(<HitTable workspaceId="ws-1" />)
  const panel = await preview()
  await panel.findByText('a paper about llms')

  const file = new File(['%PDF-1.4'], 'paper.pdf', { type: 'application/pdf' })
  fireEvent.change(panel.getByLabelText('Upload PDF for a paper about llms'), { target: { files: [file] } })

  await waitFor(() => expect(api.uploadHitPdf).toHaveBeenCalledWith('ws-1', 'h1', file))
})

test('the preview panel hides the PDF-getting options once a hit is already imported or manually acquired', async () => {
  const hit: Hit = { ...baseHit, acquisition_status: 'imported' }
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: [hit], next_cursor: null })

  renderWithClient(<HitTable workspaceId="ws-1" />)
  const panel = await preview()
  await panel.findByText('a paper about llms')

  expect(panel.queryByRole('link', { name: 'Search by title' })).not.toBeInTheDocument()
  expect(panel.queryByLabelText('Upload PDF for a paper about llms')).not.toBeInTheDocument()
})

test('the trailing ⋮ button opens a menu with Relevant, Maybe and Not relevant…', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  await pool().findByText('a paper about llms')
  fireEvent.pointerDown(pool().getByRole('button', { name: 'Hit actions' }))

  expect(await screen.findByRole('menuitem', { name: 'Relevant' })).toBeInTheDocument()
  expect(screen.getByRole('menuitem', { name: 'Maybe' })).toBeInTheDocument()
  expect(screen.getByRole('menuitem', { name: 'Not relevant…' })).toBeInTheDocument()
})

test('right-clicking a row opens the same menu', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  fireEvent.contextMenu(await pool().findByText('a paper about llms'))

  expect(await screen.findByRole('menuitem', { name: 'Relevant' })).toBeInTheDocument()
})

test('marking relevant from the ⋮ menu sends only stage1_status', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  await pool().findByText('a paper about llms')
  fireEvent.pointerDown(pool().getByRole('button', { name: 'Hit actions' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Relevant' }))

  await waitFor(() => expect(api.patchSearchHit).toHaveBeenCalledWith('ws-1', 'h1', { stage1_status: 'relevant' }))
})

test('reviewing a hit patches it into the pool in place, without re-fetching the pool', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  await pool().findByText('a paper about llms')
  const callsBeforeClick = vi.mocked(api.listSearchHits).mock.calls.length

  fireEvent.pointerDown(pool().getByRole('button', { name: 'Hit actions' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Relevant' }))

  await waitFor(() => expect(api.patchSearchHit).toHaveBeenCalled())
  expect(api.listSearchHits).toHaveBeenCalledTimes(callsBeforeClick)
})

test('picking a reason under Not relevant… sends stage1_status and the reason together', async () => {
  renderWithClient(<HitTable workspaceId="ws-1" />)
  await pool().findByText('a paper about llms')
  fireEvent.pointerDown(pool().getByRole('button', { name: 'Hit actions' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Not relevant…' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: 'duplicate' }))

  await waitFor(() =>
    expect(api.patchSearchHit).toHaveBeenCalledWith('ws-1', 'h1', {
      stage1_status: 'not_relevant',
      stage1_exclude_reason: 'duplicate',
    }),
  )
})

test('a failed review shows an error message', async () => {
  vi.spyOn(api, 'patchSearchHit').mockRejectedValue(new Error('Review failed'))
  renderWithClient(<HitTable workspaceId="ws-1" />)
  await pool().findByText('a paper about llms')
  fireEvent.pointerDown(pool().getByRole('button', { name: 'Hit actions' }))
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Maybe' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Review failed')
})

test('stays virtualized: a large hit pool renders far fewer rows than it has hits', async () => {
  const manyHits: Hit[] = Array.from({ length: 200 }, (_, i) => ({ ...baseHit, id: `h${i}`, normalized_title: `hit-${i}` }))
  vi.spyOn(api, 'listSearchHits').mockResolvedValue({ items: manyHits, next_cursor: null })

  renderWithClient(<HitTable workspaceId="ws-1" />)
  await pool().findByText('hit-0')

  const rowMenuButtons = pool().getAllByRole('button', { name: 'Hit actions' })
  expect(rowMenuButtons.length).toBeGreaterThan(0)
  expect(rowMenuButtons.length).toBeLessThan(50)
})

test('at the bottom with no known next page, real new progress triggers exactly one refetch — never on its own', async () => {
  // A single hit with next_cursor: null means hasNextPage is false from the very first render, and a 1-item
  // list is trivially "scrolled to the bottom" — this isolates the fallback path (no known next page, but the
  // worker found more) from the ordinary fetchNextPage path, which a bigger pool would also exercise.
  const runAt = (arxivRawCount: number) => ({
    id: 'run-1', workspace_id: 'ws-1', query_text: 'q', filters_json: {}, sources_json: ['arxiv'],
    status: 'running', started_at: '2026-09-24T00:00:00Z', stopped_at: null,
    stats_json: { per_source_raw_count: { arxiv: arxivRawCount } },
  })

  const { client, rerender } = renderWithClient(<HitTable workspaceId="ws-1" run={runAt(10) as never} />)
  await pool().findByText('a paper about llms')
  expect(api.listSearchHits).toHaveBeenCalledTimes(1) // the first run tick only sets a baseline, nothing to refetch yet

  const rerenderWithClient = (run: unknown) =>
    rerender(
      <QueryClientProvider client={client}>
        <HitTable workspaceId="ws-1" run={run as never} />
      </QueryClientProvider>,
    )

  // A poll tick reporting the same total (nothing new) must not trigger a refetch.
  rerenderWithClient(runAt(10))
  await waitFor(() => expect(pool().getByText('a paper about llms')).toBeInTheDocument())
  expect(api.listSearchHits).toHaveBeenCalledTimes(1)

  // Real new progress (raw count grew) while sitting at the bottom triggers exactly one refetch.
  rerenderWithClient(runAt(25))
  await waitFor(() => expect(api.listSearchHits).toHaveBeenCalledTimes(2))

  // Acknowledged — a further tick with no additional progress must not trigger yet another one.
  rerenderWithClient(runAt(25))
  await new Promise((resolve) => setTimeout(resolve, 10))
  expect(api.listSearchHits).toHaveBeenCalledTimes(2)
})

test('a failed import shows an error message', async () => {
  vi.spyOn(api, 'importSearchHits').mockRejectedValue(new Error('Import failed'))
  renderWithClient(<HitTable workspaceId="ws-1" />)
  const panel = await preview()
  await panel.findByText('a paper about llms')

  fireEvent.click(panel.getByRole('button', { name: 'Add PDF' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Import failed')
})

test('"Import all with PDF in this filter" imports every hit still pending in the pool, not just one', async () => {
  vi.spyOn(api, 'importSearchHits').mockResolvedValue({ imported: 1, failed: 0 })
  renderWithClient(<HitTable workspaceId="ws-1" />)
  await pool().findByText('a paper about llms')

  fireEvent.click(screen.getByRole('button', { name: 'Import all with PDF in this filter' }))

  await waitFor(() => expect(api.importSearchHits).toHaveBeenCalledWith('ws-1', undefined))
})

test('a failed bulk import shows an error message', async () => {
  vi.spyOn(api, 'importSearchHits').mockRejectedValue(new Error('Bulk import failed'))
  renderWithClient(<HitTable workspaceId="ws-1" />)
  await pool().findByText('a paper about llms')

  fireEvent.click(screen.getByRole('button', { name: 'Import all with PDF in this filter' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Bulk import failed')
})
