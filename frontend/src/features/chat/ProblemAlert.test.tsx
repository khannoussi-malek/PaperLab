// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type ChatScope } from '@/api/client'
import { ProblemAlert } from './ProblemAlert'

const problem = { message: 'This paper is not indexed yet.', retryable: false, reindex: true }
afterEach(() => { cleanup(); vi.restoreAllMocks() })

function mount(scope: ChatScope) {
  vi.spyOn(api, 'embeddingStatus').mockResolvedValue({ rebuild: null } as never)
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ProblemAlert scope={scope} problem={problem} onRetry={() => {}} /></QueryClientProvider>)
}

test('a hit with a paper re-indexes that paper, not the hit id', async () => {
  const reingest = vi.spyOn(api, 'reingestPaper').mockResolvedValue({} as never)
  mount({ kind: 'hit', workspaceId: 'w1', id: 'h1', paperId: 'p7' })
  fireEvent.click(await screen.findByRole('button', { name: 'Re-index' }))
  await waitFor(() => expect(reingest).toHaveBeenCalledWith('p7'))
})

test('a hit with no paper has no Re-index button', async () => {
  mount({ kind: 'hit', workspaceId: 'w1', id: 'h1' })
  expect(screen.queryByRole('button', { name: 'Re-index' })).toBeNull()
})

test('a paper scope still re-indexes the paper', async () => {
  const reingest = vi.spyOn(api, 'reingestPaper').mockResolvedValue({} as never)
  mount({ kind: 'paper', id: 'p1' })
  fireEvent.click(screen.getByRole('button', { name: 'Re-index' }))
  await waitFor(() => expect(reingest).toHaveBeenCalledWith('p1'))
})
