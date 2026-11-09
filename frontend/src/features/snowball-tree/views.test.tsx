// @vitest-environment jsdom
import { act, render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { api, type ProvenanceOut } from '@/api/client'
import { SnowballTreeTab } from './SnowballTreeTab'

// The canvas library cannot draw in jsdom: stand in with one button per node.
vi.mock('react-force-graph-2d', () => ({
  default: (p: any) => (
    <div data-testid="force">
      {p.graphData.nodes.map((n: any) => <button key={n.id} onClick={() => p.onNodeClick(n)}>{`map:${n.id}`}</button>)}
    </div>
  ),
}))
vi.stubGlobal('ResizeObserver', class { cb: any; constructor(cb: any) { this.cb = cb } observe() { this.cb([{ contentRect: { width: 800, height: 600 } }]) } disconnect() {} })

const data: ProvenanceOut = {
  truncated: false,
  roots: [{ id: 'root:r1', label: 'transformers', hit_count: 3, on_tree: 3, excluded_hidden: 0 }],
  nodes: [
    { id: 'A', title: 'Seed paper', level: 0, decision: 'relevant', snowballed: [], paths: 1, year: 2020 },
    { id: 'B', title: 'Excluded one', level: 1, decision: 'not_relevant', snowballed: [], paths: 1, year: 2018 },
    { id: 'C', title: 'Included child', level: 1, decision: 'relevant', snowballed: [], paths: 2 },
  ],
  links: [
    { parent: 'root:r1', child: 'A', kind: 'cites', run_id: 'r1', created_at: '2026-01-01T00:00:00Z' },
    { parent: 'A', child: 'B', kind: 'cites', run_id: 's1', created_at: '2026-01-02T00:00:00Z' },
    { parent: 'A', child: 'C', kind: 'cited_by', run_id: 's1', created_at: '2026-01-02T00:00:01Z' },
  ],
  levels: [
    { level: 0, found: 1, already_known: 0, included: 1, go_further: 0, stopped: 0, done: false, saturated: false },
    { level: 1, found: 2, already_known: 0, included: 1, go_further: 0, stopped: 0, done: true, saturated: false },
  ],
}
function setup(d: ProvenanceOut = data) {
  localStorage.setItem('snowball-tree-view:w1', 'tree')
  vi.spyOn(queries, 'useProvenance').mockReturnValue({ data: d, isPending: false, error: null } as any)
  vi.spyOn(queries, 'usePaths').mockReturnValue({ data: undefined } as any)
  vi.spyOn(queries, 'useSearchHit').mockReturnValue({ data: undefined } as any)
  vi.spyOn(api, 'snowballNext').mockResolvedValue([])
  vi.spyOn(api, 'listSearchRuns').mockResolvedValue([] as any)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><SnowballTreeTab workspaceId="w1" /></QueryClientProvider>)
}
beforeEach(() => localStorage.setItem('snowball-tree-view:w1', 'tree')) // these tests are about the Tree view
afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear() })
const panel = () => within(screen.getByRole('complementary'))
const view = (name: string) => fireEvent.click(screen.getByRole('button', { name }))

test('Radial: clicking a paper opens the side panel', () => {
  setup(); view('Radial')
  fireEvent.click(screen.getByRole('button', { name: 'Included child, level 1, included' }))
  expect(panel().getByText('Included child')).toBeTruthy()
})

test('Radial: titles show only on hover or focus', () => {
  setup(); view('Radial')
  const b = screen.getByRole('button', { name: 'Included child, level 1, included' })
  expect(screen.queryByText('Included child')).toBeNull()
  fireEvent.focus(b)
  expect(screen.getByText('Included child')).toBeTruthy()
})

test('Radial: ring labels', () => {
  setup(); view('Radial')
  expect(screen.getByLabelText('Radial view of the snowball tree').textContent).toContain('Level 1')
})

test('Outline: clicking a paper opens the side panel', () => {
  setup(); view('Outline')
  fireEvent.click(screen.getByRole('treeitem', { name: /Included child/ }))
  expect(panel().getByText('Included child')).toBeTruthy()
})

test('Map: clicking a paper opens the side panel, and Key papers is a toggle', async () => {
  setup(); view('Map')
  fireEvent.click(await screen.findByRole('button', { name: 'map:C' }))
  expect(panel().getByText('Included child')).toBeTruthy()
  const toggle = screen.getByRole('button', { name: 'Key papers' })
  fireEvent.click(toggle)
  expect(toggle.getAttribute('aria-pressed')).toBe('true')
})

test('switching views keeps the selection and the filters', async () => {
  setup()
  fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'relevant' } })
  fireEvent.click(screen.getByRole('button', { name: 'Included child, level 1, included' }))
  view('Outline')
  expect(panel().getByText('Included child')).toBeTruthy()
  expect((screen.getByLabelText('Decision') as HTMLSelectElement).value).toBe('relevant')
  expect(screen.getByRole('treeitem', { name: /Included child/ }).getAttribute('aria-selected')).toBe('true')
  view('Radial')
  expect(screen.getByRole('button', { name: 'Included child, level 1, included' }).getAttribute('aria-pressed')).toBe('true')
})

test('Outline fades the same papers the Tree fades', () => {
  setup()
  fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'relevant' } })
  const fadedTree = screen.getAllByRole('button').filter((b) => b.getAttribute('data-faded') === 'true').map((b) => b.getAttribute('aria-label')!.split(',')[0])
  view('Outline')
  const fadedOutline = screen.getAllByRole('treeitem').filter((b) => b.getAttribute('data-faded') === 'true').map((b) => b.textContent!.replace(/^(cites|cited by|search) /, '').split(' · ')[0])
  expect(fadedOutline.sort()).toEqual(fadedTree.sort())
})

test('the view choice is remembered for the workspace', () => {
  setup(); view('Outline')
  expect(localStorage.getItem('snowball-tree-view:w1')).toBe('outline')
})

test('Map: names its frame, and Key papers lists the key papers as buttons that select', async () => {
  setup(); view('Map')
  expect(await screen.findByLabelText('Map of the snowball tree')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Key papers' }))
  fireEvent.click(screen.getByRole('button', { name: 'Included child' })) // the only paper with more than one route
  expect(panel().getByText('Included child')).toBeTruthy()
})

test('Map: leaves out "parent not recorded" boxes', async () => {
  const withUnknown = { ...data, nodes: [...data.nodes, { id: 'run:x:unknown', title: 'x', level: 0, decision: null, snowballed: [], paths: 1 }] } as ProvenanceOut
  setup(withUnknown); view('Map')
  await screen.findByRole('button', { name: 'map:A' })
  expect(screen.queryByRole('button', { name: 'map:run:x:unknown' })).toBeNull()
})

test('Radial: a focused paper gets a focus ring', () => {
  setup(); view('Radial')
  const b = screen.getByRole('button', { name: 'Included child, level 1, included' })
  fireEvent.focus(b)
  expect(document.querySelector('[data-ring="focus"]')).toBeTruthy()
  fireEvent.blur(b)
  expect(document.querySelector('[data-ring="focus"]')).toBeNull()
})

test('Map: Key papers says so when no paper has more than one route', async () => {
  setup({ ...data, nodes: data.nodes.map((n) => ({ ...n, paths: 1 })) }); view('Map')
  await screen.findByRole('button', { name: 'map:A' })
  fireEvent.click(screen.getByRole('button', { name: 'Key papers' }))
  expect(screen.getByText('No paper is reached by more than one route yet. Key papers appear as snowballing links them.')).toBeTruthy()
  expect(screen.queryByRole('list', { name: 'Key papers' })).toBeNull()
})

// Live crash, 2026-11-09: a pointer move and a pointer up in the same batch made the state updater read a drag ref
// that pointerup had already cleared ("Cannot read properties of null (reading 'x')").
test.each(['Tree', 'Radial'])('%s: releasing the mouse in the same update as a drag move does not crash', (name) => {
  setup(); view(name)
  const frame = document.querySelector('.cursor-grab') as HTMLElement
  fireEvent.pointerDown(frame, { clientX: 100, clientY: 100 })
  expect(() => act(() => {
    fireEvent.pointerMove(frame, { clientX: 140, clientY: 120 })
    fireEvent.pointerUp(frame)
  })).not.toThrow()
})
