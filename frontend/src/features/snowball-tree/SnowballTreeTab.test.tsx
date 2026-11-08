// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, within, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { api, type ProvenanceOut } from '@/api/client'
import { SnowballTreeTab } from './SnowballTreeTab'

const data: ProvenanceOut = {
  truncated: false,
  roots: [{ id: 'root:r1', label: 'transformers', hit_count: 18308, on_tree: 12 }],
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
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><SnowballTreeTab workspaceId="w1" /></QueryClientProvider>)
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

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
