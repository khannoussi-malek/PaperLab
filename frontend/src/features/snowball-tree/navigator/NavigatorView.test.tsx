// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { sileo } from 'sileo'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, type Hit, type ProvenanceOut } from '@/api/client'
import { NavigatorView } from './NavigatorView'

const node = (id: string, level: number, extra: object = {}) => ({ id, title: `Paper ${id}`, level, snowballed: [], paths: 1, decision: null, ...extra })
const link = (parent: string, child: string, kind: string) => ({ parent, child, kind, run_id: 'r1', created_at: '2026-01-01T00:00:00Z' })
const prov = (over: Partial<ProvenanceOut> = {}) => ({
  truncated: false,
  roots: [{ id: 'root:r1', label: 'graph search', hit_count: 2, on_tree: 2, excluded_hidden: 0 }],
  nodes: [node('A', 0, { snowballed: ['cites', 'cited_by'], relevance: 4 }), node('B', 1), node('C', 1), node('D', 0)],
  links: [link('root:r1', 'A', 'search'), link('root:r1', 'D', 'search'), link('A', 'B', 'cites'), link('A', 'C', 'cited_by')],
  levels: [],
  ...over,
}) as unknown as ProvenanceOut

const hit = (id: string, over: object = {}) => ({
  id, title: `Paper ${id}`, abstract: `Abstract of ${id}`, authors: ['Ada'], year: 2020, venue: 'Venue', paper_id: null, acquisition_status: 'candidate',
  doi: null, sources: [], suggestion: null, suggestion_relevance: null, suggestion_reason: null, suggestion_quotes: null, ...over,
}) as unknown as Hit

function setup(data = prov(), nav = '') {
  if (!location.hash.includes('navPaper')) history.replaceState(null, '', nav ? `#/workspaces/w1?tab=tree&nav=${nav}` : '#/workspaces/w1?tab=tree')
  vi.spyOn(api, 'getSearchHit').mockImplementation(async (_w, id) => hit(id, id === 'A' ? { suggestion: 'include', suggestion_relevance: 4, suggestion_reason: 'It tests the point.', suggestion_quotes: ['we show X'] } : {}))
  vi.spyOn(api, 'listWorkspacePapers').mockResolvedValue([{ id: 'p9', title: 'Library only paper', authors: [], year: 2019, venue: null, abstract: null, has_pdf: false, oa_url: null }] as never)
  vi.spyOn(api, 'provenance').mockResolvedValue(data)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (d: ProvenanceOut) => <QueryClientProvider client={client}><NavigatorView workspaceId="w1" data={d} /></QueryClientProvider>
  const view = render(ui(data))
  return { rerender: (d: ProvenanceOut) => view.rerender(ui(d)) }
}
const row = (title: string) => screen.getByText(title).closest('li') as HTMLElement
const crumbs = () => within(screen.getByRole('navigation', { name: 'Snowball path' }))

beforeEach(() => { vi.spyOn(sileo, 'info').mockImplementation((() => '') as never) })
afterEach(() => { cleanup(); vi.restoreAllMocks() })

test('the starting point lists the searches with their first papers', () => {
  setup()
  expect(screen.getByText('🔍 graph search')).toBeTruthy()
  expect(row('Paper A')).toBeTruthy()
  expect(row('Paper D')).toBeTruthy()
  expect(screen.queryByRole('navigation', { name: 'Snowball path' })).toBeNull()
})

test('Start from a paper lists matches from the tree and the library, and picking one opens its card', async () => {
  setup()
  fireEvent.change(screen.getByLabelText('Start from a paper'), { target: { value: 'library' } })
  fireEvent.click(await screen.findByRole('button', { name: /Library only paper/ }))
  expect(await within(screen.getByRole('navigation', { name: 'Snowball path' })).findByText('Library only paper')).toBeTruthy()
  expect(screen.getByText('Added by hand: no fit score')).toBeTruthy()
})

test('Start from a paper finds tree papers by title fragment', () => {
  setup()
  fireEvent.change(screen.getByLabelText('Start from a paper'), { target: { value: 'paper c' } })
  fireEvent.click(screen.getByRole('button', { name: /Paper C/ }))
  expect(crumbs().getByText('Paper C')).toBeTruthy()
  expect(location.hash).toContain('nav=root:r1,A,C')
})

test('Step in grows the breadcrumb and updates the URL without a history entry', async () => {
  setup()
  const before = history.length
  fireEvent.click(within(row('Paper A')).getByRole('button', { name: 'Step in to Paper A' }))
  expect(crumbs().getByText('Paper A')).toBeTruthy()
  expect(location.hash).toContain('nav=root:r1,A')
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Step in to Paper B' }))
  expect(crumbs().getByText('Paper B')).toBeTruthy()
  expect(location.hash).toContain('nav=root:r1,A,B')
  expect(history.length).toBe(before)
})

test('the tabs show counts, or (not fetched) before a snowball', () => {
  setup(prov(), 'root:r1,A')
  expect(screen.getByRole('tab', { name: 'Papers it cites (1)' })).toBeTruthy()
  expect(screen.getByRole('tab', { name: 'Papers citing it (1)' })).toBeTruthy()
  cleanup()
  setup(prov(), 'root:r1,A,B')
  expect(screen.getByRole('tab', { name: 'Papers it cites (not fetched)' })).toBeTruthy()
  expect(screen.getByRole('tab', { name: 'Papers citing it (not fetched)' })).toBeTruthy()
})

test('the card shows Find citing & cited papers as a button when never snowballed', async () => {
  setup(prov(), 'root:r1,A,B')
  const snow = vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: {} })
  fireEvent.click(screen.getAllByRole('button', { name: 'Find citing & cited papers' })[0])
  await waitFor(() => expect(snow).toHaveBeenCalledWith('w1', { seed_hit_ids: ['B'], seed_paper_ids: [], backward: true, forward: true }))
})

test('the card shows the fit, the reason, a quote and the abstract', async () => {
  setup(prov(), 'root:r1,A')
  expect(await screen.findByText('It tests the point.')).toBeTruthy()
  expect(screen.getByText('For your question:')).toBeTruthy()
  expect(screen.getByText(/we show X/)).toBeTruthy()
  expect(screen.getByText('Abstract of A')).toBeTruthy()
  expect(screen.getByText('fits 4/5', { exact: false })).toBeTruthy()
})

test('Grab calls snowball for only that hit, then shows the done line', async () => {
  setup(prov(), 'root:r1,A')
  const snow = vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 3, skipped_seeds: [], errors: {} })
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Grab next papers for Paper B' }))
  expect(within(row('Paper B')).getByText('Grabbing…')).toBeTruthy()
  await waitFor(() => expect(snow).toHaveBeenCalledWith('w1', { seed_hit_ids: ['B'], seed_paper_ids: [], backward: true, forward: true }))
  expect(snow).toHaveBeenCalledTimes(1)
  expect(await within(row('Paper B')).findByText('✓ grabbed · 0 cites · 0 citing')).toBeTruthy()
  expect(crumbs().getByText('Paper A')).toBeTruthy() // still standing on A
})

test('a Grab error shows the friendly text', async () => {
  setup(prov(), 'root:r1,A')
  vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: { B: 'HTTP 429 from api.semanticscholar.org' } })
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Grab next papers for Paper B' }))
  expect(await within(row('Paper B')).findByText('Semantic Scholar refused: add a free key in Settings → Paper sources.')).toBeTruthy()
})

test('Go further records both directions and grabs only when a direction is missing', async () => {
  setup(prov(), 'root:r1,A,B')
  const branch = vi.spyOn(api, 'setBranch').mockResolvedValue({} as never)
  const snow = vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: {} })
  fireEvent.click(screen.getByRole('button', { name: 'Go further' }))
  await waitFor(() => expect(snow).toHaveBeenCalledTimes(1))
  expect(branch).toHaveBeenCalledWith('w1', { hit_id: 'B', state: 'go_further', directions: ['cites', 'cited_by'], reason: null })
  expect(crumbs().getByText('Paper B')).toBeTruthy()
  cleanup()
  snow.mockClear()
  setup(prov(), 'root:r1,A')
  fireEvent.click(screen.getByRole('button', { name: 'Go further' }))
  await waitFor(() => expect(branch).toHaveBeenCalledTimes(2))
  expect(snow).not.toHaveBeenCalled()
})

test('Stop here records the branch with a reason field and greys out the list', async () => {
  const data = prov({ nodes: prov().nodes.map((n) => (n.id === 'A' ? { ...n, branch: { state: 'stopped', directions: [], reason: null } } : n)) })
  setup(data, 'root:r1,A')
  expect(screen.getByLabelText('Reason')).toBeTruthy()
  expect(screen.getByTestId('next-papers').className).toContain('opacity-50')
  expect(within(row('Paper B')).getByRole('button', { name: 'Step in to Paper B' })).toBeTruthy() // still works
})

test('clicking Stop here saves the branch', async () => {
  setup(prov(), 'root:r1,A')
  const branch = vi.spyOn(api, 'setBranch').mockResolvedValue({} as never)
  fireEvent.click(screen.getByRole('button', { name: 'Stop here' }))
  await waitFor(() => expect(branch).toHaveBeenCalledWith('w1', { hit_id: 'A', state: 'stopped', directions: [], reason: null }))
})

test.each([
  ['needs_criteria', 'Set your review question in Search & screen first.'],
  ['prescreen_running', 'The AI is pre-screening this workspace; try again when it finishes.'],
  ['suggest_timeout', 'The AI took too long; try again.'],
])('Summarise now shows the message for %s', async (code, text) => {
  setup(prov(), 'root:r1,A')
  vi.spyOn(api, 'suggestHit').mockRejectedValue(new ApiError(code, 409, { detail: code }))
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Summarise Paper B' }))
  expect(await within(row('Paper B')).findByText(text)).toBeTruthy()
})

test('Summarise now retries with confirm_remote after the owner agrees', async () => {
  setup(prov(), 'root:r1,A')
  const suggest = vi.spyOn(api, 'suggestHit').mockRejectedValueOnce(new ApiError('x', 409, { detail: 'remote_model_needs_confirm', host: 'api.example.com' })).mockResolvedValue(hit('B', { suggestion_relevance: 2 }))
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Summarise Paper B' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Send' }))
  await waitFor(() => expect(suggest).toHaveBeenLastCalledWith('w1', 'B', true))
})

test('a refetch keeps the current paper and the breadcrumb', () => {
  const { rerender } = setup(prov(), 'root:r1,A')
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Step in to Paper B' }))
  rerender(prov({ nodes: prov().nodes.map((n) => (n.id === 'B' ? { ...n, decision: 'relevant' } : n)) }))
  expect(crumbs().getByText('Paper B')).toBeTruthy()
  expect(crumbs().getByText('Paper A')).toBeTruthy()
  expect(location.hash).toContain('nav=root:r1,A,B')
})

test('a stale path is cut at the first missing entry with a notice', () => {
  setup(prov(), 'root:r1,A,ZZ')
  expect(sileo.info).toHaveBeenCalledWith(expect.objectContaining({ title: 'This path changed; showing the part that still exists.' }))
  expect(crumbs().getByText('Paper A')).toBeTruthy()
  expect(location.hash).toContain('nav=root:r1,A')
  expect(location.hash).not.toContain('ZZ')
})

test('navPaper opens on that library paper and is replaced by nav', async () => {
  history.replaceState(null, '', '#/workspaces/w1?tab=tree&navPaper=p9')
  setup(prov())
  expect(await within(screen.getByRole('navigation', { name: 'Snowball path' })).findByText('Library only paper')).toBeTruthy()
  expect(screen.getByText('Added by hand: no fit score')).toBeTruthy()
  expect(screen.getAllByRole('button', { name: 'Find citing & cited papers' })).toHaveLength(1)
  expect(location.hash).toContain('nav=root:hand,paper:p9')
  expect(location.hash).not.toContain('navPaper')
})

test('40 rows make no per-row hit requests', async () => {
  const kids = Array.from({ length: 40 }, (_, i) => `K${i}`)
  const data = prov({ nodes: [...prov().nodes, ...kids.map((k) => node(k, 1))], links: [...prov().links, ...kids.map((k) => link('A', k, 'cites'))] })
  setup(data, 'root:r1,A')
  await screen.findByText('It tests the point.')
  expect(screen.getAllByRole('listitem').length).toBeGreaterThanOrEqual(40)
  expect(api.getSearchHit).toHaveBeenCalledTimes(1) // the card only
})

test('a fetched direction leaves the other one a Find button for just that direction', async () => {
  const data = prov({ nodes: prov().nodes.map((n) => (n.id === 'B' ? { ...n, snowballed: ['cites'] } : n)) })
  setup(data, 'root:r1,A,B')
  fireEvent.click(screen.getByRole('tab', { name: 'Papers citing it (not fetched)' }))
  const snow = vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: {} })
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Papers citing it (not fetched)' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Find papers citing it' }))
  await waitFor(() => expect(snow).toHaveBeenCalledWith('w1', { seed_hit_ids: ['B'], seed_paper_ids: [], backward: false, forward: true }))
})

test('cancelling the remote question says Not summarised.', async () => {
  setup(prov(), 'root:r1,A')
  vi.spyOn(api, 'suggestHit').mockRejectedValue(new ApiError('x', 409, { detail: 'remote_model_needs_confirm', host: 'h' }))
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Summarise Paper B' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
  expect(await screen.findByText('Not summarised.')).toBeTruthy()
})

test('a row with a reason shows it under the title', () => {
  const data = prov({ nodes: prov().nodes.map((n) => (n.id === 'B' ? { ...n, reason: 'Tests the point on small data.' } : n)) })
  setup(data, 'root:r1,A')
  expect(within(row('Paper B')).getByText('Tests the point on small data.')).toBeTruthy()
})
