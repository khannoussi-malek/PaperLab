// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import { FoundPdfsNotice } from './FoundPdfsNotice'

afterEach(() => vi.restoreAllMocks())

const find = (id: string, title: string) => ({ id: `e-${id}`, paper_id: id, title, created_at: '2026-10-14T12:00:00Z' })
const show = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FoundPdfsNotice />
    </QueryClientProvider>,
  )

it('lists the finds as reader links in a polite status region', async () => {
  vi.spyOn(api, 'foundPdfs').mockResolvedValue([find('a', 'Alpha'), find('b', 'Beta')])
  show()
  const region = await screen.findByRole('status')
  expect(region).toHaveTextContent('Found free PDFs for 2 papers saved without one:')
  expect(screen.getByRole('link', { name: 'Alpha' })).toHaveAttribute('href', expect.stringContaining('a'))
})

it('Dismiss posts exactly the shown ids, then asks again', async () => {
  const list = vi.spyOn(api, 'foundPdfs').mockResolvedValueOnce([find('a', 'Alpha'), find('b', 'Beta')]).mockResolvedValue([])
  const seen = vi.spyOn(api, 'markFoundPdfsSeen').mockResolvedValue(undefined)
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }))
  await waitFor(() => expect(seen).toHaveBeenCalledWith(['e-a', 'e-b']))
  await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
  expect(list).toHaveBeenCalledTimes(2)
})

it('renders nothing when there are no finds', async () => {
  const list = vi.spyOn(api, 'foundPdfs').mockResolvedValue([])
  show()
  await waitFor(() => expect(list).toHaveBeenCalled())
  expect(screen.queryByRole('status')).toBeNull()
})
