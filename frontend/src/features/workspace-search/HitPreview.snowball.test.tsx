// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type Hit } from '@/api/client'
import { HitPreview } from './HitPreview'

const hit = { id: 'h1', title: 'Paper', normalized_title: 'paper', sources: [], acquisition_status: 'imported' } as unknown as Hit
afterEach(() => { cleanup(); vi.restoreAllMocks() })

function mount() {
  vi.spyOn(api, 'hitPaths').mockResolvedValue([])
  vi.spyOn(api, 'provenance').mockResolvedValue({ roots: [], nodes: [], links: [], levels: [], truncated: false } as never)
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <HitPreview hit={hit} workspaceId="w1" onReview={() => {}} onAddPdf={() => {}} addPdfPending={false} onUpload={() => {}} uploadPending={false} />
    </QueryClientProvider>,
  )
}

test('Find citing & cited papers snowballs only this hit, both ways, and says what it found', async () => {
  const snowball = vi.spyOn(api, 'snowball').mockResolvedValue({ new_hits: 3, skipped_seeds: [], errors: {} } as never)
  mount()
  fireEvent.click(screen.getByRole('button', { name: 'Find citing & cited papers' }))
  await waitFor(() => expect(snowball).toHaveBeenCalledWith('w1', { seed_hit_ids: ['h1'], seed_paper_ids: [], backward: true, forward: true }))
  expect(await screen.findByText('Found 3 new papers.')).toBeTruthy()
})

test('a failed snowball shows a friendly error', async () => {
  vi.spyOn(api, 'snowball').mockRejectedValue(new Error('HTTP 429 from api.semanticscholar.org'))
  mount()
  fireEvent.click(screen.getByRole('button', { name: 'Find citing & cited papers' }))
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Semantic Scholar refused'))
})

test('Navigate from here opens the Snowball tree on this hit', () => {
  history.replaceState(null, '', '#/workspaces/w1?tab=search')
  mount()
  expect(screen.getByRole('link', { name: 'Navigate from here' }).getAttribute('href')).toBe('#/workspaces/w1?tab=tree&navPaper=h1')
})
