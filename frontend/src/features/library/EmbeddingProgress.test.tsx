// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { EmbeddingProgress, timeLeft } from './EmbeddingProgress'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const show = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <EmbeddingProgress paperId="p1" />
    </QueryClientProvider>,
  )

test('says how many passages are done and fills the bar to match', async () => {
  vi.spyOn(api, 'embeddingProgress').mockResolvedValue({ done: 1024, total: 31302 })
  show()
  expect(await screen.findByText(`Preparing search: ${(1024).toLocaleString()} of ${(31302).toLocaleString()} passages`))
    .toBeTruthy()
  expect(screen.getByRole('progressbar', { name: 'Preparing search' }).getAttribute('aria-valuenow')).toBe('3')
})

test('shows nothing before there are chunks to count', async () => {
  const progress = vi.spyOn(api, 'embeddingProgress').mockResolvedValue({ done: 0, total: 0 })
  const { container } = show()
  await vi.waitFor(() => expect(progress).toHaveBeenCalled())
  expect(container.textContent).toBe('')
  expect(screen.queryByRole('progressbar')).toBeNull()
})

test.each([
  [10, 1000, 0, 30, 'about 50 minutes left'],
  [500, 1000, 0, 500, 'about 8 minutes left'],
  [990, 1000, 900, 90, 'less than a minute left'],
  [1000, 40000, 0, 200, 'about 2 hours left'],
])('reads the time left from the speed so far: %i of %i', (done, total, startDone, seconds, words) => {
  expect(timeLeft(done, total, startDone, seconds)).toBe(words)
})

test('says nothing until the speed means something', () => {
  expect(timeLeft(10, 1000, 0, 10)).toBeNull() // too soon
  expect(timeLeft(10, 1000, 10, 60)).toBeNull() // nothing moved
})
