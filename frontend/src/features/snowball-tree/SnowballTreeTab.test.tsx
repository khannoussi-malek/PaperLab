// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import type { ProvenanceOut } from '@/api/client'
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

function setup() {
  vi.spyOn(queries, 'useProvenance').mockReturnValue({ data, isPending: false, error: null } as any)
  vi.spyOn(queries, 'usePaths').mockReturnValue({ data: undefined } as any)
  render(<SnowballTreeTab workspaceId="w1" />)
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
  expect(screen.getByRole('button', { name: /^transformers, search/ }).getAttribute('data-faded')).toBe('true')
})

test('a faded ancestor keeps C reachable when only level 1 is shown', () => {
  setup()
  fireEvent.change(screen.getByLabelText('Level'), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText('Decision'), { target: { value: 'relevant' } })
  expect(screen.getByRole('button', { name: /^Seed paper/ }).getAttribute('data-faded')).toBe('true')
  expect(screen.getByRole('button', { name: /^Included child/ }).getAttribute('data-faded')).toBe('false')
})
