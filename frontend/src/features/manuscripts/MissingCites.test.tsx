// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { MissingCites } from './MissingCites'

const keys = (n: number) => Array.from({ length: n }, (_, i) => ({ key: `k${i}`, file: i === 0 ? 'refs/a.tex' : 'main.tex', line: i + 3 }))
function show(compiledAt = 't1', onJump = vi.fn()) {
  const ui = (at: string) => (
    <QueryClientProvider client={client}><MissingCites manuscriptId="m" compiledAt={at} onJump={onJump} /></QueryClientProvider>
  )
  const r = render(ui(compiledAt))
  return { ...r, again: (at: string) => r.rerender(ui(at)), onJump }
}
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
afterEach(() => { vi.restoreAllMocks(); client.clear() })

test('renders nothing when every key resolves', async () => {
  const spy = vi.spyOn(api, 'missingKeys').mockResolvedValue([])
  const { container } = show()
  await vi.waitFor(() => expect(spy).toHaveBeenCalled())
  expect(container).toBeEmptyDOMElement()
})

test('lists keys with file and line, and a click jumps there', async () => {
  vi.spyOn(api, 'missingKeys').mockResolvedValue(keys(2))
  const { onJump } = show()
  expect(await screen.findByText('Cited but not found')).toBeTruthy()
  expect(screen.getByText(/match no paper in your library or your \.bib files, so LaTeX prints \[\?\]/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /k0.*refs\/a\.tex:3/ }))
  expect(onJump).toHaveBeenCalledWith('refs/a.tex', 3)
  expect(screen.getByRole('button', { name: /k1.*main\.tex:4/ })).toBeTruthy()
})

test('caps at 20 rows with "and N more"', async () => {
  vi.spyOn(api, 'missingKeys').mockResolvedValue(keys(23))
  show()
  expect(await screen.findByText('and 3 more')).toBeTruthy()
  expect(screen.getAllByRole('button')).toHaveLength(20)
})

test('refetches when compiledAt changes', async () => {
  const spy = vi.spyOn(api, 'missingKeys').mockResolvedValue(keys(1))
  const { again } = show('t1')
  await screen.findByText('k0')
  again('t2')
  await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
})
