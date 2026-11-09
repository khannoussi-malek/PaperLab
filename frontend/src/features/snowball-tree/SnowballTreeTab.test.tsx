// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, within, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { api, type ProvenanceOut } from '@/api/client'
import { SnowballTreeTab } from './SnowballTreeTab'

vi.stubGlobal('ResizeObserver', class { cb: any; constructor(cb: any) { this.cb = cb } observe() { this.cb([{ contentRect: { width: 800, height: 600 } }]) } disconnect() {} })

const data: ProvenanceOut = {
  truncated: false,
  roots: [{ id: 'root:r1', label: 'transformers', hit_count: 18308, on_tree: 12, excluded_hidden: 0 }],
  nodes: [
    { id: 'A', title: 'Seed paper', level: 0, decision: 'relevant', snowballed: ['cites'], paths: 1 },
    { id: 'B', title: 'Excluded one', level: 1, decision: 'not_relevant', snowballed: [], paths: 1 },
    { id: 'C', title: 'Included child', level: 1, decision: 'relevant', snowballed: [], paths: 1 },
    { id: 'Z', title: 'Lonely seed', level: 0, decision: null, snowballed: [], paths: 1,
      zero_found_error: 'Semantic Scholar refused: add a free key in Settings → Paper sources.' },
  ],
  links: [
    { parent: 'root:r1', child: 'A', kind: 'cites', run_id: 'r1', created_at: '2026-01-01T00:00:00Z' },
    { parent: 'root:r1', child: 'Z', kind: 'cites', run_id: 'r1', created_at: '2026-01-01T00:00:01Z' },
    { parent: 'A', child: 'B', kind: 'cites', run_id: 's1', created_at: '2026-01-02T00:00:00Z' },
    { parent: 'A', child: 'C', kind: 'cited_by', run_id: 's1', created_at: '2026-01-02T00:00:01Z' },
  ],
  levels: [
    { level: 0, found: 2, already_known: 0, included: 1, go_further: 1, stopped: 0, done: false, saturated: false },
    { level: 1, found: 2, already_known: 0, included: 1, go_further: 0, stopped: 0, done: true, saturated: false },
  ],
}

function setup(d: ProvenanceOut = data) {
  vi.spyOn(queries, 'useProvenance').mockReturnValue({ data: d, isPending: false, error: null } as any)
  vi.spyOn(queries, 'usePaths').mockReturnValue({ data: undefined } as any)
  vi.spyOn(queries, 'useSearchHit').mockReturnValue({ data: undefined } as any)
  vi.spyOn(api, 'snowballNext').mockResolvedValue([])
  vi.spyOn(api, 'listSearchRuns').mockResolvedValue([
    { id: 'r1', query_text: 'transformers' }, { id: 's1', query_text: 'Snowball: Seed paper' },
  ] as any)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><SnowballTreeTab workspaceId="w1" /></QueryClientProvider>)
}
beforeEach(() => localStorage.setItem('snowball-tree-view:w1', 'tree')) // these tests are about the Tree view
afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear() })

test('search-root boxes show hit count and how many are on the tree', () => {
  setup()
  expect(screen.getByText('18,308 hits · 12 on the tree')).toBeTruthy()
})

test('level headers render', () => {
  setup()
  expect(screen.getByText('Level 0 · 2 found · 0 already known · 1 included · 1 to go further · 0 stopped')).toBeTruthy()
  expect(screen.getByText('Level 1 · 2 found · 0 already known · 1 included · 0 to go further · 0 stopped · done')).toBeTruthy()
})

test('a legend names the line styles and the colours', () => {
  setup()
  const legend = screen.getByLabelText('Legend')
  for (const t of ['it cites', 'cited by', 'included', 'excluded', 'not screened']) expect(within(legend).getByText(t)).toBeTruthy()
})

test('colours follow the decision via data attributes', () => {
  setup()
  expect(screen.getByRole('button', { name: 'Seed paper, level 0, included' }).getAttribute('data-decision')).toBe('relevant')
  expect(screen.getByRole('button', { name: 'Excluded one, level 1, excluded' }).getAttribute('data-decision')).toBe('not_relevant')
  expect(screen.getByRole('button', { name: 'Lonely seed, level 0, not screened' }).getAttribute('data-decision')).toBe('none')
})

test('zero-found seed renders with its error', () => {
  setup()
  expect(screen.getByText('0 found')).toBeTruthy()
  expect(screen.getByText(/Semantic Scholar refused: add a free key in Settings → Paper sources\./)).toBeTruthy()
})

test('clicking a box selects it', () => {
  setup()
  const b = screen.getByRole('button', { name: 'Included child, level 1, included' })
  fireEvent.click(b)
  expect(b.getAttribute('aria-pressed')).toBe('true')
  expect(within(screen.getByRole('complementary')).getByText('Included child')).toBeTruthy()
})

test('filtering to included keeps the faded ancestors of C', () => {
  setup()
  fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'relevant' } })
  expect(screen.queryByRole('button', { name: /Excluded one/ })).toBeNull()
  expect(screen.queryByRole('button', { name: /Lonely seed/ })).toBeNull()
  expect(screen.getByRole('button', { name: /Included child/ })).toBeTruthy()
  expect(screen.getByRole('button', { name: /^transformers, search/ }).getAttribute('data-faded')).toBe('false')
})

test('a faded ancestor keeps C reachable when only level 1 is shown', () => {
  setup()
  fireEvent.change(screen.getByLabelText('Level'), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'relevant' } })
  expect(screen.getByRole('button', { name: /^Seed paper/ }).getAttribute('data-faded')).toBe('true')
  expect(screen.getByRole('button', { name: /^Included child/ }).getAttribute('data-faded')).toBe('false')
})

const branched: ProvenanceOut = {
  ...data,
  nodes: [
    ...data.nodes,
    { id: 'S', title: 'Stopped one', level: 1, decision: null, snowballed: [], paths: 1, branch: { state: 'stopped', directions: [], reason: 'too general' } },
    { id: 'S1', title: 'Below the stop', level: 2, decision: null, snowballed: [], paths: 1 },
    { id: 'G', title: 'Going on', level: 1, decision: null, snowballed: [], paths: 1, branch: { state: 'go_further', directions: ['cites'], reason: null } },
  ],
  links: [
    ...data.links,
    { parent: 'A', child: 'S', kind: 'cites', run_id: 's1', created_at: '2026-01-02T00:00:02Z' },
    { parent: 'A', child: 'G', kind: 'cites', run_id: 's1', created_at: '2026-01-02T00:00:03Z' },
    { parent: 'S', child: 'S1', kind: 'cites', run_id: 's2', created_at: '2026-01-03T00:00:00Z' },
  ],
}

test('boxes carry a branch mark: open arrow for go further, bar for stopped', () => {
  setup(branched)
  expect(screen.getByRole('button', { name: 'Going on, level 1, not screened, go further' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Stopped one, level 1, not screened, stopped' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Seed paper, level 0, included' })).toBeTruthy()
})

test('stopped subtrees are folded until Show stopped is on', () => {
  setup(branched)
  expect(screen.queryByRole('button', { name: /^Below the stop/ })).toBeNull()
  expect(screen.getByRole('button', { name: 'Show stopped' }).getAttribute('aria-pressed')).toBe('false')
  fireEvent.click(screen.getByRole('button', { name: 'Show stopped' }))
  expect(screen.getByRole('button', { name: /^Below the stop/ })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Hide stopped' }))
  expect(screen.queryByRole('button', { name: /^Below the stop/ })).toBeNull()
})

test('Find citing & cited papers snowballs both ways at once and the box says Snowballing…', async () => {
  setup()
  const snowball = vi.spyOn(api, 'snowball').mockReturnValue(new Promise(() => {}) as any)
  fireEvent.click(screen.getByRole('button', { name: 'Included child, level 1, included' }))
  fireEvent.click(screen.getByRole('button', { name: 'Find citing & cited papers' }))
  await waitFor(() => expect(snowball).toHaveBeenCalledWith('w1', { seed_hit_ids: ['C'], seed_paper_ids: [], backward: true, forward: true }))
  expect(await screen.findAllByText('Snowballing…')).toHaveLength(2) // the box and the disabled button
})

const withNode = (node: object, root: object = {}): ProvenanceOut => ({
  ...data, roots: [{ ...data.roots[0], ...root }], nodes: [...data.nodes, node as any],
  links: [...data.links, { parent: 'root:r1', child: (node as any).id, kind: 'cites', run_id: 'r1', created_at: '2026-01-01T00:00:09Z' }],
})

test('a raw Semantic Scholar 429 on a zero-found seed shows the plan sentence', () => {
  setup(withNode({
    id: 'X', title: 'Refused seed', level: 0, decision: null, snowballed: [], paths: 1,
    zero_found_error: "Client error '429 Too Many Requests' for url 'https://api.semanticscholar.org/graph/v1/paper/x/citations'",
  }))
  expect(screen.getAllByText('Semantic Scholar refused: add a free key in Settings → Paper sources.').length).toBe(2)
})

test('a seed that ran cleanly and found nothing still shows 0 found, with no error text', () => {
  setup(withNode({ id: 'X', title: 'Quiet seed', level: 0, decision: null, snowballed: ['cites'], paths: 1, zero_found_error: '' }))
  const box = screen.getByRole('button', { name: /^Quiet seed/ })
  expect(within(box).getByText('0 found')).toBeTruthy()
  expect(box.querySelectorAll('span.line-clamp-1, span.line-clamp-2, span.truncate')).toHaveLength(1) // only the title
})

test('a search root says how many excluded hits the cap left off', () => {
  setup({ ...data, roots: [{ ...data.roots[0], excluded_hidden: 1200 }] })
  expect(screen.getByText('18,308 hits · 12 on the tree · 1200 excluded hidden')).toBeTruthy()
})

test('the deepest level says saturated, and that wins over done', () => {
  const levels = data.levels.map((l) => (l.level === 1 ? { ...l, done: true, saturated: true } : l))
  setup({ ...data, levels })
  expect(screen.getByText(/^Level 1 · .* · saturated$/)).toBeTruthy()
  expect(screen.queryByText(/ · done$/)).toBeNull()
})

test('boxes are in the DOM parent before child, roots to leaves', () => {
  setup()
  const names = screen.getAllByRole('button').map((b) => b.getAttribute('aria-label') ?? '').filter((n) => /level|search/.test(n))
  const at = (prefix: string) => names.findIndex((n) => n.startsWith(prefix))
  expect(at('transformers')).toBeLessThan(at('Seed paper'))
  expect(at('Seed paper')).toBeLessThan(at('Excluded one'))
  expect(at('Seed paper')).toBeLessThan(at('Included child'))
})

test('selecting a box moves focus to the side panel heading', () => {
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Included child, level 1, included' }))
  const heading = within(screen.getByRole('complementary')).getByRole('heading', { name: 'Included child' })
  expect(document.activeElement).toBe(heading)
})

test('folding away the selected box clears the selection', () => {
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Included child, level 1, included' }))
  expect(screen.getByRole('complementary')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Fold Seed paper' }))
  expect(screen.queryByRole('complementary')).toBeNull()
})

test('the Run filter lists the snowball runs too, by their query text', async () => {
  setup()
  await waitFor(() => expect(within(screen.getByLabelText('Run')).getAllByRole('option').map((o) => o.textContent)).toEqual(['All', 'transformers', 'Snowball: Seed paper']))
})

test('a failed Find citing & cited papers shows its error in an alert', async () => {
  setup()
  vi.spyOn(api, 'snowball').mockRejectedValue(new Error('Semantic Scholar is switched off'))
  fireEvent.click(screen.getByRole('button', { name: 'Included child, level 1, included' }))
  fireEvent.click(screen.getByRole('button', { name: 'Find citing & cited papers' }))
  expect((await screen.findByRole('alert')).textContent).toBe('Semantic Scholar is switched off')
})

test('the branch mark tooltip uses the direction words', () => {
  setup(branched)
  const mark = screen.getByRole('button', { name: /^Going on/ }).querySelector('[data-branch="go_further"]')
  expect(mark?.getAttribute('title')).toBe('Go further: Its references')
})

const manyPapers = (n: number, relevantIdx = -1): ProvenanceOut => ({
  ...data,
  nodes: Array.from({ length: n }, (_, i) => ({
    id: `P${i}`, title: `Paper ${i}`, level: 0, decision: i === relevantIdx ? 'relevant' : null, snowballed: [], paths: 1,
  })) as any,
  links: Array.from({ length: n }, (_, i) => ({ parent: 'root:r1', child: `P${i}`, kind: 'cites', run_id: 'r1', created_at: `2026-01-01T00:00:${String(i).padStart(2, '0')}Z` })),
  levels: [data.levels[0]],
})

test('a paper box shows a long title on two lines, wide enough for about 40 characters', () => {
  const title = 'A very long paper title that goes on and on about transformers'
  setup(withNode({ id: 'L', title, level: 0, decision: null, snowballed: [], paths: 1 }))
  const box = screen.getByRole('button', { name: new RegExp(`^${title}`) })
  const span = within(box).getByText(title)
  expect(span.className).toContain('line-clamp-2')
  expect(span.getAttribute('title')).toBe(title)
  expect(parseInt(box.style.width, 10)).toBeGreaterThanOrEqual(240)
  expect(box.textContent).toContain(title.slice(0, 40))
})

test('a search with 13 papers starts folded and says how many; clicking unfolds', () => {
  setup(manyPapers(13))
  expect(screen.queryByRole('button', { name: /^Paper 0/ })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: /^13 papers: show/ }))
  expect(screen.getByRole('button', { name: /^Paper 0/ })).toBeTruthy()
  expect(screen.queryByRole('button', { name: /^13 papers: show/ })).toBeNull()
})

test('a search with 12 papers starts open', () => {
  setup(manyPapers(12))
  expect(screen.getByRole('button', { name: /^Paper 0/ })).toBeTruthy()
  expect(screen.queryByText(/papers: show/)).toBeNull()
})

test('with a filter active, a search that has matches starts open', () => {
  setup(manyPapers(13, 5))
  fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'relevant' } })
  expect(screen.getByRole('button', { name: /^Paper 5/ })).toBeTruthy()
  expect(screen.queryByText(/papers: show/)).toBeNull()
})

test('changing the Level filter pans the canvas to the first visible box', () => {
  setup()
  const wrap = () => document.querySelector('[style*="translate"]') as HTMLElement
  const before = wrap().style.transform
  fireEvent.change(screen.getByLabelText('Level'), { target: { value: '1' } })
  const after = wrap().style.transform
  expect(after).not.toBe(before)
  const [, x, y] = /translate\((-?[\d.]+)px, (-?[\d.]+)px\)/.exec(after)!.map(Number)
  const first = screen.getByRole('button', { name: /^Excluded one/ })
  expect(x + parseFloat(first.style.left)).toBeGreaterThanOrEqual(0)
  expect(y + parseFloat(first.style.top)).toBeLessThan(600)
  expect(y + parseFloat(first.style.top)).toBeGreaterThanOrEqual(0)
})

test('a hand-unfolded search stays open when a filter is applied', () => {
  setup(manyPapers(13, 5))
  fireEvent.click(screen.getByRole('button', { name: /^13 papers: show/ }))
  fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'relevant' } })
  expect(screen.getByRole('button', { name: /^Paper 5/ })).toBeTruthy()
})

test('a box with a 0 found line clamps its title to one line', () => {
  setup()
  const box = screen.getByRole('button', { name: /^Lonely seed/ })
  expect(within(box).getByText('Lonely seed').className).toContain('line-clamp-1')
})

test('the fold control reads its visible text first, then the search', () => {
  setup(manyPapers(13))
  expect(screen.getByRole('button', { name: '13 papers: show, transformers' })).toBeTruthy()
})

test('a search that grows past 12 papers on a refetch does not fold under the user', () => {
  setup(manyPapers(12))
  expect(screen.getByRole('button', { name: /^Paper 0/ })).toBeTruthy()
  vi.spyOn(queries, 'useProvenance').mockReturnValue({ data: manyPapers(13), isPending: false, error: null } as any)
  fireEvent.click(screen.getByRole('button', { name: 'Radial' }))
  fireEvent.click(screen.getByRole('button', { name: 'Tree' }))
  expect(screen.getByRole('button', { name: /^Paper 0/ })).toBeTruthy()
})

test('a refetch with the same filters leaves the pan where the user put it', () => {
  setup()
  fireEvent.change(screen.getByLabelText('Level'), { target: { value: '1' } })
  const wrap = () => document.querySelector('[style*="translate"]') as HTMLElement
  fireEvent.wheel(wrap().parentElement!, { deltaY: -100 }) // user zooms: the translate only follows a re-pan
  const before = wrap().style.transform
  const more = { ...data, nodes: [...data.nodes, { id: 'N', title: 'New seed', level: 0, decision: null, snowballed: [], paths: 1 }],
    links: [...data.links, { parent: 'root:r1', child: 'N', kind: 'cites', run_id: 'r1', created_at: '2026-01-01T00:00:09Z' }] } as ProvenanceOut
  vi.spyOn(queries, 'useProvenance').mockReturnValue({ data: more, isPending: false, error: null } as any)
  fireEvent.click(screen.getByRole('button', { name: /^Excluded one/ }))
  expect(wrap().style.transform).toBe(before)
})
