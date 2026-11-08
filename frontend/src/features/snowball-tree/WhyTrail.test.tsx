// @vitest-environment jsdom
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { WhyTrail } from './WhyTrail'

const link = (parent: string, child: string, kind: string) => ({ parent, child, kind, run_id: 'r1', created_at: null })
const prov = {
  roots: [{ id: 'root:r1', label: 'transformers', hit_count: 3, on_tree: 3 }],
  nodes: [
    { id: 'A', title: 'Paper A', level: 0, snowballed: [], paths: 1 },
    { id: 'B', title: 'Paper B', level: 1, snowballed: [], paths: 2 },
  ],
  links: [], levels: [],
}
function setup(paths: any[][] | undefined) {
  vi.spyOn(queries, 'useProvenance').mockReturnValue({ data: prov } as any)
  vi.spyOn(queries, 'usePaths').mockReturnValue({ data: paths } as any)
  render(<WhyTrail workspaceId="w1" hitId="H" />)
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

test('draws the first path with the kind on each snowball arrow, and counts the others', () => {
  setup([
    [link('root:r1', 'A', 'search'), link('A', 'B', 'cites'), link('B', 'H', 'cited_by')],
    [link('root:r1', 'B', 'search'), link('B', 'H', 'cited_by')],
  ])
  expect(screen.getByText('transformers → Paper A → (it cites) → Paper B → (cited by) → this paper')).toBeTruthy()
  const more = screen.getByRole('button', { name: '+1 other path' })
  expect(more.getAttribute('aria-expanded')).toBe('false')
  expect(screen.queryByText('transformers → Paper B → (cited by) → this paper')).toBeNull()
  fireEvent.click(more)
  expect(screen.getByText('transformers → Paper B → (cited by) → this paper')).toBeTruthy()
})

test('the other-paths count comes from the node, not from the listed paths', () => {
  vi.spyOn(queries, 'useProvenance').mockReturnValue({ data: { ...prov, nodes: [...prov.nodes, { id: 'H', title: 'H', level: 2, snowballed: [], paths: 31 }] } } as any)
  vi.spyOn(queries, 'usePaths').mockReturnValue({ data: [[link('root:r1', 'H', 'search')], [link('root:r1', 'B', 'search'), link('B', 'H', 'cited_by')]] } as any)
  render(<WhyTrail workspaceId="w1" hitId="H" />)
  fireEvent.click(screen.getByRole('button', { name: '+30 other paths' }))
  expect(screen.getByText('…and 29 more not listed')).toBeTruthy()
})

test('a single path has no "also reached" line; no path renders nothing', () => {
  setup([[link('root:r1', 'H', 'search')]])
  expect(screen.getByText('transformers → this paper')).toBeTruthy()
  expect(screen.queryByRole('button', { name: /other path/ })).toBeNull()
  cleanup()
  setup([])
  expect(screen.queryByText(/this paper/)).toBeNull()
})
