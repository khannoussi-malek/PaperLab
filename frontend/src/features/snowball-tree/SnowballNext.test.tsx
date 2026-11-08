// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { SnowballNext } from './SnowballNext'

const items = [
  { hit_id: 'h1', paper_id: null, title: 'Alpha paper', directions_left: ['cites', 'cited_by'] },
  { hit_id: null, paper_id: 'p2', title: 'Beta paper', directions_left: ['cited_by'] },
]
function setup(list = items) {
  vi.spyOn(api, 'snowballNext').mockResolvedValue(list as any)
  const never = new Promise<never>(() => {})
  const run = vi.spyOn(api, 'runSnowballNext').mockReturnValue(never as any)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><SnowballNext workspaceId="w1" /></QueryClientProvider>)
  return run
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

test('lists each branch with the directions still to run', async () => {
  setup()
  expect(await screen.findByText('Alpha paper')).toBeTruthy()
  expect(screen.getByText('Beta paper')).toBeTruthy()
  expect(screen.getByText('Its references, Papers citing it')).toBeTruthy()
  expect(screen.getByText('Papers citing it')).toBeTruthy()
})

test('Run all calls the run endpoint once, then is disabled and says Snowballing…', async () => {
  const run = setup()
  fireEvent.click(await screen.findByRole('button', { name: 'Run all' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Snowballing…' })).toBeTruthy())
  expect((screen.getByRole('button', { name: 'Snowballing…' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Snowballing…' }))
  expect(run).toHaveBeenCalledTimes(1)
  expect(run).toHaveBeenCalledWith('w1')
})

test('an empty list renders nothing', async () => {
  setup([])
  await waitFor(() => expect(api.snowballNext).toHaveBeenCalled())
  expect(screen.queryByRole('button', { name: 'Run all' })).toBeNull()
})

test('after a batch, says how many are left', async () => {
  setup()
  vi.spyOn(api, 'runSnowballNext').mockResolvedValue({ new_hits: 3, skipped_seeds: [], errors: {}, remaining: 5 })
  fireEvent.click(await screen.findByRole('button', { name: 'Run all' }))
  expect(await screen.findByText('5 more left: Run all again')).toBeTruthy()
})

test('after Run all, says how many new papers and shows a friendly error', async () => {
  setup()
  vi.spyOn(api, 'runSnowballNext').mockResolvedValue({
    new_hits: 3, skipped_seeds: [], remaining: 0,
    errors: { h1: "Client error '429 Too Many Requests' for url 'https://api.semanticscholar.org/x'" },
  })
  fireEvent.click(await screen.findByRole('button', { name: 'Run all' }))
  expect(await screen.findByText('3 new papers. Semantic Scholar refused: add a free key in Settings → Paper sources.')).toBeTruthy()
})
