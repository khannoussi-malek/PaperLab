// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import { keys } from '@/api/queries'
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

it('a failed Dismiss says why and keeps the notice', async () => {
  vi.spyOn(api, 'foundPdfs').mockResolvedValue([find('a', 'Alpha')])
  vi.spyOn(api, 'markFoundPdfsSeen').mockRejectedValue(new Error('PaperLab could not save that.'))
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }))
  expect(await screen.findByText('PaperLab could not save that.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Alpha' })).toBeInTheDocument()
})

it('refreshes the library when more finds arrive, so their "No PDF yet" badges go', async () => {
  vi.spyOn(api, 'foundPdfs').mockResolvedValueOnce([find('a', 'Alpha')]).mockResolvedValue([find('a', 'Alpha'), find('b', 'Beta')])
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  render(<QueryClientProvider client={client}><FoundPdfsNotice /></QueryClientProvider>)
  await screen.findByRole('link', { name: 'Alpha' })
  expect(invalidate).not.toHaveBeenCalledWith({ queryKey: keys.papers }) // the first list is not news
  await client.refetchQueries({ queryKey: keys.foundPdfs })
  await screen.findByRole('link', { name: 'Beta' })
  expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.papers })
})

it('renders nothing when there are no finds', async () => {
  const list = vi.spyOn(api, 'foundPdfs').mockResolvedValue([])
  show()
  await waitFor(() => expect(list).toHaveBeenCalled())
  expect(screen.queryByRole('status')).toBeNull()
})

it('polls every 60 seconds', async () => {
  vi.spyOn(api, 'foundPdfs').mockResolvedValue([])
  const client = new QueryClient()
  render(<QueryClientProvider client={client}><FoundPdfsNotice /></QueryClientProvider>)
  await waitFor(() => expect(client.getQueryCache().find({ queryKey: keys.foundPdfs })).toBeDefined())
  expect(client.getQueryCache().find({ queryKey: keys.foundPdfs })?.observers[0]?.options.refetchInterval).toBe(60_000)
})
