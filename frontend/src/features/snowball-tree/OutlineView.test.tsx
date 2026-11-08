// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import type { ProvenanceOut } from '@/api/client'
import { OutlineView } from './OutlineView'

const data: ProvenanceOut = {
  truncated: false,
  roots: [{ id: 'root:r1', label: 'transformers', hit_count: 3, on_tree: 3, excluded_hidden: 0 }],
  nodes: [
    { id: 'A', title: 'Seed paper', level: 0, decision: 'relevant', snowballed: [], paths: 1, branch: { state: 'go_further', directions: ['cites'], reason: null } },
    { id: 'B', title: 'Excluded one', level: 1, decision: 'not_relevant', snowballed: [], paths: 1, branch: { state: 'stopped', directions: [], reason: 'too general' } },
    { id: 'C', title: 'Child cited by', level: 1, decision: null, snowballed: [], paths: 1 },
  ],
  links: [
    { parent: 'root:r1', child: 'A', kind: 'cites', run_id: 'r1', created_at: '2026-01-01T00:00:00Z' },
    { parent: 'A', child: 'B', kind: 'cites', run_id: 's1', created_at: '2026-01-02T00:00:00Z' },
    { parent: 'A', child: 'C', kind: 'cited_by', run_id: 's1', created_at: '2026-01-02T00:00:01Z' },
  ],
  levels: [],
}
const mutate = vi.fn()
function setup(hidden = new Set<string>(), onSelect = vi.fn()) {
  vi.spyOn(queries, 'useSetBranch').mockReturnValue({ mutate } as any)
  render(<OutlineView workspaceId="w1" data={data} selected={null} onSelect={onSelect} hidden={hidden} />)
  return onSelect
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); mutate.mockClear() })
const item = (re: RegExp) => screen.getByRole('treeitem', { name: re })

test('rows read kind, title, level, decision and the branch tag', () => {
  setup()
  expect(screen.getByRole('tree')).toBeTruthy()
  expect(item(/Seed paper/).textContent).toBe('cites Seed paper · L0 · included · go further: Its references')
  expect(item(/Excluded one/).textContent).toBe('cites Excluded one · L1 · excluded · stopped: too general')
  expect(item(/Child cited by/).textContent).toBe('cited by Child cited by · L1 · not screened')
})

test('arrows move, Right unfolds, Left folds, Enter opens the panel', () => {
  const onSelect = setup()
  const tree = screen.getByRole('tree')
  act(() => item(/transformers/).focus())
  fireEvent.keyDown(tree, { key: 'ArrowDown' })
  expect(document.activeElement).toBe(item(/Seed paper/))
  fireEvent.keyDown(tree, { key: 'ArrowLeft' }) // fold A
  expect(screen.queryByRole('treeitem', { name: /Excluded one/ })).toBeNull()
  expect(item(/Seed paper/).getAttribute('aria-expanded')).toBe('false')
  fireEvent.keyDown(tree, { key: 'ArrowRight' }) // unfold
  expect(item(/Excluded one/)).toBeTruthy()
  fireEvent.keyDown(tree, { key: 'ArrowDown' })
  expect(document.activeElement).toBe(item(/Excluded one/))
  fireEvent.keyDown(tree, { key: 'ArrowUp' })
  expect(document.activeElement).toBe(item(/Seed paper/))
  fireEvent.keyDown(tree, { key: 'Enter' })
  expect(onSelect).toHaveBeenCalledWith('A')
})

test('g, s and u set the branch of the focused row', () => {
  setup()
  const tree = screen.getByRole('tree')
  act(() => item(/Child cited by/).focus())
  fireEvent.keyDown(tree, { key: 'g' })
  expect(mutate).toHaveBeenLastCalledWith({ hit_id: 'C', state: 'go_further', directions: ['cites', 'cited_by'], reason: null })
  fireEvent.keyDown(tree, { key: 's' })
  expect(mutate).toHaveBeenLastCalledWith({ hit_id: 'C', state: 'stopped', directions: [], reason: null })
  fireEvent.keyDown(tree, { key: 'u' })
  expect(mutate).toHaveBeenLastCalledWith({ hit_id: 'C', state: null, directions: [], reason: null })
})

test('shows the keys hint', () => {
  setup()
  expect(screen.getByText('Keys: ↑↓ move · → open · ← close · Enter details · g go further · s stop · u undecided')).toBeTruthy()
})

test('filtered-out papers are faded like the tree fades them', () => {
  setup(new Set(['A', 'B'])) // B has no kept descendant and drops out; A stays, faded, above C
  expect(screen.queryByRole('treeitem', { name: /Excluded one/ })).toBeNull()
  expect(item(/Seed paper/).getAttribute('data-faded')).toBe('true')
  expect(item(/Child cited by/).getAttribute('data-faded')).toBe('false')
})
