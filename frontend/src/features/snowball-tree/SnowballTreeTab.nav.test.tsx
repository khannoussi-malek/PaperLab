// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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

test('navPaper opens the card even with no search runs', async () => {
  history.replaceState(null, '', '#/workspaces/w1?tab=tree&navPaper=p9')
  vi.spyOn(api, 'provenance').mockResolvedValue({ truncated: false, roots: [], nodes: [], links: [], levels: [] } as never)
  vi.spyOn(api, 'snowballNext').mockResolvedValue([])
  vi.spyOn(api, 'listSearchRuns').mockResolvedValue([])
  vi.spyOn(api, 'listWorkspacePapers').mockResolvedValue([{ id: 'p9', title: 'Solo paper', authors: [], year: null, venue: null, abstract: null, has_pdf: false, oa_url: null }] as never)
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SnowballTreeTab workspaceId="w1" /></QueryClientProvider>)
  expect(await screen.findByText('Added by hand: no fit score')).toBeTruthy()
  expect(screen.queryByText(/Nothing to draw yet/)).toBeNull()
})

test('switching away from Navigate clears nav so a reload does not force it back', async () => {
  setup('#/workspaces/w1?tab=tree&nav=root:r1,A')
  await screen.findByRole('navigation', { name: 'Snowball path' })
  fireEvent.click(screen.getByRole('button', { name: 'Outline' }))
  expect(location.hash).not.toContain('nav=')
})

test('clicking Navigate while on Navigate keeps nav in the URL', async () => {
  setup('#/workspaces/w1?tab=tree&nav=root:r1,A')
  await screen.findByRole('navigation', { name: 'Snowball path' })
  fireEvent.click(screen.getByRole('button', { name: 'Navigate' }))
  expect(location.hash).toContain('nav=root:r1,A')
  expect(screen.getByRole('navigation', { name: 'Snowball path' })).toBeTruthy()
})

const EMPTY = { truncated: false, roots: [], nodes: [], links: [], levels: [] } as never
function setupEmpty(papers: unknown[]) {
  history.replaceState(null, '', '#/workspaces/w1?tab=tree')
  vi.spyOn(api, 'provenance').mockResolvedValue(EMPTY)
  vi.spyOn(api, 'snowballNext').mockResolvedValue([])
  vi.spyOn(api, 'listSearchRuns').mockResolvedValue([])
  vi.spyOn(api, 'listWorkspacePapers').mockResolvedValue(papers as never)
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SnowballTreeTab workspaceId="w1" /></QueryClientProvider>)
}

test('no runs, one library paper: Navigate lists it and Step in opens its card', async () => {
  setupEmpty([{ id: 'p1', title: 'Solo paper', authors: [], year: null, venue: null, abstract: null, has_pdf: false, oa_url: null }])
  expect(await screen.findByText('Papers in this workspace')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /Step in/ }))
  expect(await screen.findByText('Added by hand: no fit score')).toBeTruthy()
})

test('no runs and no papers: says nothing is here yet, with both links', async () => {
  setupEmpty([])
  expect(await screen.findByText(/Nothing here yet/)).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Papers tab' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Search & screen' })).toBeTruthy()
})

test('Tree view with no runs hints at Navigate and the button switches', async () => {
  localStorage.setItem('snowball-tree-view:w1', 'tree')
  setupEmpty([])
  fireEvent.click(await screen.findByRole('button', { name: 'Switch to Navigate' }))
  expect(await screen.findByText(/Nothing here yet/)).toBeTruthy()
})
