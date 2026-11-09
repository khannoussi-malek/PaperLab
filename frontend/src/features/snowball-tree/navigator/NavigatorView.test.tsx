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

function setup(data = prov(), nav = '', hitA: object = {}) {
  if (!location.hash.includes('navPaper')) history.replaceState(null, '', nav ? `#/workspaces/w1?tab=tree&nav=${nav}` : '#/workspaces/w1?tab=tree')
  vi.spyOn(api, 'getSearchHit').mockImplementation(async (_w, id) => hit(id, id === 'A' ? { suggestion: 'include', suggestion_relevance: 4, suggestion_reason: null, suggestion_note: 'It tests the point.', suggestion_quotes: ['we show X'], ...hitA } : {}))
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
  fireEvent.click(within(row('Paper A')).getByRole('button', { name: 'Step in ›' }))
  expect(crumbs().getByText('Paper A')).toBeTruthy()
  expect(location.hash).toContain('nav=root:r1,A')
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Step in ›' }))
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

test('a paper with no route says it was added by hand, not reached by 0 routes', async () => {
  setup(prov({ nodes: [node('A', 0, { paths: 0, snowballed: ['cites', 'cited_by'], relevance: 4 }), node('B', 1), node('C', 1), node('D', 0)] }), 'root:r1,A')
  expect(await screen.findByText(/Level 0 · added by hand · /)).toBeTruthy()
  expect(screen.queryByText(/reached by 0/)).toBeNull()
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
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: '⤓ Grab next papers' }))
  expect(within(row('Paper B')).getByText('Grabbing…')).toBeTruthy()
  await waitFor(() => expect(snow).toHaveBeenCalledWith('w1', { seed_hit_ids: ['B'], seed_paper_ids: [], backward: true, forward: true }))
  expect(snow).toHaveBeenCalledTimes(1)
  expect(await within(row('Paper B')).findByText('✓ grabbed · 0 cites · 0 citing')).toBeTruthy()
  expect(crumbs().getByText('Paper A')).toBeTruthy() // still standing on A
})

test('a Grab error shows the friendly text', async () => {
  setup(prov(), 'root:r1,A')
  vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: [], errors: { B: 'HTTP 429 from api.semanticscholar.org' } })
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: '⤓ Grab next papers' }))
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
  expect(within(row('Paper B')).getByRole('button', { name: 'Step in ›' })).toBeTruthy() // still works
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
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Summarise now' }))
  expect(await within(row('Paper B')).findByText(text)).toBeTruthy()
})

test('Summarise now retries with confirm_remote after the owner agrees', async () => {
  setup(prov(), 'root:r1,A')
  const suggest = vi.spyOn(api, 'suggestHit').mockRejectedValueOnce(new ApiError('x', 409, { detail: 'remote_model_needs_confirm', host: 'api.example.com' })).mockResolvedValue(hit('B', { suggestion_relevance: 2 }))
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Summarise now' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Send' }))
  await waitFor(() => expect(suggest).toHaveBeenLastCalledWith('w1', 'B', true))
})

test('a refetch keeps the current paper and the breadcrumb', () => {
  const { rerender } = setup(prov(), 'root:r1,A')
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Step in ›' }))
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
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Summarise now' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
  expect(await screen.findByText('Not summarised.')).toBeTruthy()
})

test('a row with a reason shows it under the title', async () => {
  const data = prov({ nodes: prov().nodes.map((n) => (n.id === 'B' ? { ...n, reason: 'Tests the point on small data.' } : n)) })
  setup(data, 'root:r1,A')
  expect(await screen.findByText('Tests the point on small data.')).toBeTruthy()
})

test('an include shows the AI note; an exclude shows its note, never the raw code', async () => {
  setup(prov(), 'root:r1,A', { suggestion: 'exclude', suggestion_reason: 'wrong_topic', suggestion_note: 'Not about graphs.' })
  expect(await screen.findByText('Not about graphs.')).toBeTruthy()
  expect(screen.queryByText('wrong_topic')).toBeNull()
})

test('a reload of nav=root:hand,paper:x with no tree node keeps both entries, no notice', async () => {
  setup(prov(), 'root:hand,paper:p9')
  expect(await crumbs().findByText('Library only paper')).toBeTruthy()
  expect(crumbs().getByText('Added by hand')).toBeTruthy()
  expect(sileo.info).not.toHaveBeenCalled()
  expect(location.hash).toContain('nav=root:hand,paper:p9')
})

test('a reload of nav=root:hand,paper:gone where gone is not in the library shows the stale notice and keeps root:hand', async () => {
  setup(prov(), 'root:hand,paper:gone')
  await waitFor(() => expect(sileo.info).toHaveBeenCalledWith(expect.objectContaining({ title: 'This path changed; showing the part that still exists.' })))
  expect(screen.queryByText('Paper gone')).toBeNull()
  expect(location.hash).toContain('nav=root:hand')
  expect(location.hash).not.toContain('gone')
})

test('a navPaper that is neither in the tree nor in the library shows the stale notice', async () => {
  history.replaceState(null, '', '#/workspaces/w1?tab=tree&navPaper=zzz')
  setup(prov())
  await waitFor(() => expect(sileo.info).toHaveBeenCalledWith(expect.objectContaining({ title: 'This path changed; showing the part that still exists.' })))
  expect(screen.queryByRole('navigation', { name: 'Snowball path' })).toBeNull()
  expect(location.hash).not.toContain('zzz')
})

test('Step in moves focus to the new card heading; the first paint does not', () => {
  setup(prov(), 'root:r1,A')
  expect(document.activeElement).not.toBe(screen.getByRole('heading', { name: 'Paper A' }))
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Step in ›' }))
  expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Paper B' }))
})

test('a seed Semantic Scholar does not know is an error on the card button and on a row', async () => {
  setup(prov(), 'root:r1,A,B')
  vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 0, skipped_seeds: ['B'], errors: {} })
  fireEvent.click(screen.getAllByRole('button', { name: 'Find citing & cited papers' })[0])
  expect(screen.getByRole('button', { name: 'Snowballing…' })).toBeTruthy()
  expect(await screen.findByText('Skipped 1 seed(s) with no Semantic Scholar match.')).toBeTruthy()
})

test('a row whose paper was snowballed before shows the grabbed line with totals', () => {
  setup()
  expect(within(row('Paper A')).getByText('✓ grabbed · 1 cites · 1 citing')).toBeTruthy()
  expect(within(row('Paper D')).getByText('⤓ Grab next papers')).toBeTruthy()
})

test.each([
  [['no_abstract'], 'No abstract to read yet.'],
  [['model_error'], 'The AI could not read this paper.'],
])('Summarise now with flags %s says so', async (flags, text) => {
  setup(prov(), 'root:r1,A')
  vi.spyOn(api, 'suggestHit').mockResolvedValue(hit('B', { suggestion_flags: flags }))
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Summarise now' }))
  expect(await within(row('Paper B')).findByText(text)).toBeTruthy()
})

test('Summarise now with no model set up points to Settings', async () => {
  setup(prov(), 'root:r1,A')
  vi.spyOn(api, 'suggestHit').mockRejectedValue(new ApiError('no_model', 409, { detail: 'no_model' }))
  fireEvent.click(within(row('Paper B')).getByRole('button', { name: 'Summarise now' }))
  expect(await within(row('Paper B')).findByText('No AI model is set up. Add one in Settings → AI.')).toBeTruthy()
})

test('the current crumb is aria-current=page and row buttons are described by the row title', () => {
  setup(prov(), 'root:r1,A')
  expect(crumbs().getByRole('button', { name: 'Paper A' }).getAttribute('aria-current')).toBe('page')
  expect(crumbs().getByRole('button', { name: '🔍 graph search' }).getAttribute('aria-current')).toBeNull()
  const step = within(row('Paper B')).getByRole('button', { name: 'Step in ›' })
  expect(document.getElementById(step.getAttribute('aria-describedby')!)?.textContent).toBe('Paper B')
})

test('Stop here again keeps the stored reason', async () => {
  const data = prov({ nodes: prov().nodes.map((n) => (n.id === 'A' ? { ...n, branch: { state: 'stopped', directions: [], reason: 'too general' } } : n)) })
  setup(data, 'root:r1,A')
  const branch = vi.spyOn(api, 'setBranch').mockResolvedValue({} as never)
  fireEvent.click(screen.getByRole('button', { name: 'Stop here' }))
  await waitFor(() => expect(branch).toHaveBeenCalledWith('w1', { hit_id: 'A', state: 'stopped', directions: [], reason: 'too general' }))
})

test('Go further shows it is working, cannot double-run, then shows the result', async () => {
  setup(prov(), 'root:r1,A,B')
  vi.spyOn(api, 'setBranch').mockResolvedValue({} as never)
  let finish!: (v: never) => void
  const snow = vi.spyOn(api, 'snowball').mockImplementation(() => new Promise((r) => { finish = r as never }))
  const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
  const btn = screen.getByRole('button', { name: 'Go further' })
  fireEvent.click(btn)
  await waitFor(() => expect(screen.getAllByText('Snowballing…').length).toBeGreaterThan(0))
  expect((screen.getByRole('button', { name: 'Go further' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Go further' }))
  expect(snow).toHaveBeenCalledTimes(1)
  finish({ new_hits: 0, skipped_seeds: [], errors: {} } as never)
  expect(await screen.findByText('✓ grabbed · 0 cites · 0 citing')).toBeTruthy()
  await waitFor(() => expect(scroll).toHaveBeenCalled())
  expect(document.activeElement?.getAttribute('role')).toBe('tab')
})

test('Go further on a fully snowballed paper makes no call but still scrolls to the next papers', async () => {
  setup(prov(), 'root:r1,A')
  vi.spyOn(api, 'setBranch').mockResolvedValue({} as never)
  const snow = vi.spyOn(api, 'snowball')
  const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
  fireEvent.click(screen.getByRole('button', { name: 'Go further' }))
  await waitFor(() => expect(scroll).toHaveBeenCalled())
  expect(snow).not.toHaveBeenCalled()
})

test('Full details is a titled dialog with the abstract, DOI and AI note, no branch buttons, and Escape returns focus', async () => {
  setup(prov(), 'root:r1,A', { doi: '10.1/xyz', abstract: 'A'.repeat(900) })
  const button = await screen.findByRole('button', { name: 'Full details' })
  button.focus()
  fireEvent.click(button)
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('Paper A', { selector: 'h2' })).toBeTruthy()
  expect(within(dialog).getByText('A'.repeat(900))).toBeTruthy()
  expect(within(dialog).getByRole('link', { name: '10.1/xyz' })).toBeTruthy()
  expect(within(dialog).getByText('It tests the point.')).toBeTruthy()
  for (const name of [/Go further/, /Stop here/, /Undecided/, /Find citing/]) expect(within(dialog).queryByRole('button', { name })).toBeNull()
  fireEvent.keyDown(dialog, { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(document.activeElement).toBe(button)
})

test('the card groups Screening and Snowball and shows each state', async () => {
  setup(prov(), 'root:r1,A,B')
  const screening = await screen.findByRole('group', { name: 'Screening' })
  expect(within(screening).getByTestId('screening-state').textContent).toBe('Not screened')
  expect(within(screening).getByRole('button', { name: 'Include' }).getAttribute('aria-pressed')).toBe('false')
  expect(within(screen.getByRole('group', { name: 'Snowball' })).getByTestId('snowball-state').textContent).toBe('Undecided')
  expect(within(screening).getByRole('button', { name: 'Exclude' }).getAttribute('title')).toBe('Pick a reason to exclude.')
  expect(within(screening).getByText('Pick a reason to exclude.')).toBeTruthy()
})

test('an included paper and a stopped branch show their chips', async () => {
  const data = prov({ nodes: prov().nodes.map((n) => (n.id === 'B' ? { ...n, decision: 'relevant', branch: { state: 'stopped', directions: [], reason: 'too general' } } : n)) })
  setup(data, 'root:r1,A,B')
  expect((await screen.findByTestId('screening-state')).textContent).toBe('Included')
  expect(screen.getByTestId('snowball-state').textContent).toBe('Stopped: too general')
  expect(screen.getByRole('button', { name: 'Include' }).getAttribute('aria-pressed')).toBe('true')
})

test('an unfetched tab explains itself, a fetched empty one says None found.', () => {
  setup(prov(), 'root:r1,A,B')
  expect(screen.getByText('Not fetched yet.')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Find its references' })).toBeTruthy()
})

test('Go further ignores a grab that finishes after the owner moved to another paper', async () => {
  setup(prov(), 'root:r1,A,B')
  vi.spyOn(api, 'setBranch').mockResolvedValue({} as never)
  let finish!: (v: never) => void
  vi.spyOn(api, 'snowball').mockImplementation(() => new Promise((r) => { finish = r as never }))
  const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
  fireEvent.click(screen.getByRole('button', { name: 'Go further' }))
  await waitFor(() => expect(screen.getAllByText('Snowballing…').length).toBeGreaterThan(0))
  fireEvent.click(crumbs().getByRole('button', { name: 'Paper A' }))
  finish({ new_hits: 0, skipped_seeds: [], errors: {} } as never)
  await new Promise((r) => setTimeout(r, 50))
  expect(scroll).not.toHaveBeenCalled()
})

test('Full details opens at once with a loading line while the hit loads', async () => {
  setup(prov(), 'root:r1,A')
  vi.spyOn(api, 'getSearchHit').mockImplementation(() => new Promise(() => {}))
  fireEvent.click(screen.getByRole('button', { name: 'Full details' }))
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText('Loading the paper…')).toBeTruthy()
})
