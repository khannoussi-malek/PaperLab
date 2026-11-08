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
  expect(screen.getByText('cites, cited by')).toBeTruthy()
  expect(screen.getByText('cited by')).toBeTruthy()
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
