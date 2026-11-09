// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type ProvenanceOut } from '@/api/client'
import { SnowballTreeTab } from './SnowballTreeTab'

const node = (id: string, level: number) => ({ id, title: `Paper ${id}`, level, snowballed: [], paths: 1 })
const data = {
  truncated: false,
  roots: [{ id: 'root:r1', label: 'graph search', hit_count: 1, on_tree: 1, excluded_hidden: 0 }],
  nodes: [node('A', 0), node('B', 1)],
  links: [
    { parent: 'root:r1', child: 'A', kind: 'search', run_id: 'r1', created_at: '2026-01-01T00:00:00Z' },
    { parent: 'A', child: 'B', kind: 'cites', run_id: 'r1', created_at: '2026-01-01T00:00:00Z' },
  ],
  levels: [],
} as unknown as ProvenanceOut

afterEach(() => { cleanup(); vi.restoreAllMocks(); localStorage.clear() })

test('Navigate from here on the Tree opens Navigate on that paper with its primary path', async () => {
  history.replaceState(null, '', '#/workspaces/w1?tab=tree')
  localStorage.setItem('snowball-tree-view:w1', 'tree')
  vi.spyOn(api, 'provenance').mockResolvedValue(data)
  vi.spyOn(api, 'snowballNext').mockResolvedValue([])
  vi.spyOn(api, 'listSearchRuns').mockResolvedValue([])
  vi.spyOn(api, 'listWorkspacePapers').mockResolvedValue([])
  vi.spyOn(api, 'listChat').mockResolvedValue([])
  vi.spyOn(api, 'listChatModels').mockResolvedValue([])
  vi.spyOn(api, 'getSearchHit').mockImplementation(async (_w, id) => ({ id, title: `Paper ${id}`, abstract: 'x', sources: [] }) as never)
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SnowballTreeTab workspaceId="w1" /></QueryClientProvider>)
  fireEvent.click(await screen.findByText('Paper B'))
  fireEvent.click(await screen.findByRole('button', { name: 'Navigate from here' }))
  expect(await screen.findByRole('navigation', { name: 'Snowball path' })).toBeTruthy()
  expect(location.hash).toContain('nav=root:r1,A,B')
})
