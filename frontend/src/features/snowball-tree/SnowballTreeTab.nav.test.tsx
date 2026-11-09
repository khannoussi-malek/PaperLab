// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type ProvenanceOut } from '@/api/client'
import { SnowballTreeTab } from './SnowballTreeTab'

const data = {
  truncated: false,
  roots: [{ id: 'root:r1', label: 'graph search', hit_count: 1, on_tree: 1, excluded_hidden: 0 }],
  nodes: [{ id: 'A', title: 'Paper A', level: 0, snowballed: [], paths: 1 }],
  links: [{ parent: 'root:r1', child: 'A', kind: 'search', run_id: 'r1', created_at: '2026-01-01T00:00:00Z' }],
  levels: [],
} as unknown as ProvenanceOut

function setup(hash: string) {
  history.replaceState(null, '', hash)
  vi.spyOn(api, 'provenance').mockResolvedValue(data)
  vi.spyOn(api, 'snowballNext').mockResolvedValue([])
  vi.spyOn(api, 'listSearchRuns').mockResolvedValue([])
  vi.spyOn(api, 'listWorkspacePapers').mockResolvedValue([])
  vi.spyOn(api, 'getSearchHit').mockResolvedValue({ id: 'A', title: 'Paper A' } as never)
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SnowballTreeTab workspaceId="w1" /></QueryClientProvider>)
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear() })

test('Navigate is the default view when nothing is stored', async () => {
  setup('#/workspaces/w1?tab=tree')
  expect(await screen.findByLabelText('Start from a paper')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Navigate' }).getAttribute('aria-pressed')).toBe('true')
})

test('a stored choice still wins', async () => {
  localStorage.setItem('snowball-tree-view:w1', 'outline')
  setup('#/workspaces/w1?tab=tree')
  expect(await screen.findByRole('button', { name: 'Outline' })).toBeTruthy()
  expect(screen.queryByLabelText('Start from a paper')).toBeNull()
})

test('nav in the URL forces Navigate whatever is stored', async () => {
  localStorage.setItem('snowball-tree-view:w1', 'outline')
  setup('#/workspaces/w1?tab=tree&nav=root:r1,A')
  expect(await screen.findByRole('navigation', { name: 'Snowball path' })).toBeTruthy()
})
