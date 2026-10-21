// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type PaperSources } from '@/api/client'
import { PaperSourcesSettings } from './PaperSourcesSettings'

afterEach(() => vi.restoreAllMocks())

it('shows the weekly re-check switch with its helper text, and sends the flag', async () => {
  const data = { sources: [], contact_email: null, pdf_recheck_enabled: true } as unknown as PaperSources
  vi.spyOn(api, 'paperSources').mockResolvedValue(data)
  const patch = vi.spyOn(api, 'updatePaperSources').mockResolvedValue({ ...data, pdf_recheck_enabled: false })
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PaperSourcesSettings />
    </QueryClientProvider>,
  )
  const box = await screen.findByRole('checkbox', { name: 'Look for free PDFs weekly for papers saved without one' })
  expect(box).toBeChecked()
  expect(
    screen.getByText(
      'Papers saved without a PDF are re-checked for a free copy at most once a week, 25 a day, using the same sources as Add (Unpaywall, arXiv, PMC and repositories).',
    ),
  ).toBeInTheDocument()
  fireEvent.click(box)
  await waitFor(() => expect(patch).toHaveBeenCalledWith({ pdf_recheck_enabled: false }))
})

it('says so when saving the switch fails, and links the helper text to it', async () => {
  const data = { sources: [], contact_email: null, pdf_recheck_enabled: true } as unknown as PaperSources
  vi.spyOn(api, 'paperSources').mockResolvedValue(data)
  vi.spyOn(api, 'updatePaperSources').mockRejectedValue(new Error('Could not save'))
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PaperSourcesSettings />
    </QueryClientProvider>,
  )
  const box = await screen.findByRole('checkbox', { name: 'Look for free PDFs weekly for papers saved without one' })
  expect(box).toHaveAccessibleDescription(/re-checked for a free copy/)
  fireEvent.click(box)
  expect(await screen.findByText('Could not save')).toBeInTheDocument()
})

it('toggling the switch refreshes only the paper sources, not discovery', async () => {
  const data = { sources: [], contact_email: null, pdf_recheck_enabled: true } as unknown as PaperSources
  vi.spyOn(api, 'paperSources').mockResolvedValue(data)
  vi.spyOn(api, 'updatePaperSources').mockResolvedValue({ ...data, pdf_recheck_enabled: false })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  render(
    <QueryClientProvider client={client}>
      <PaperSourcesSettings />
    </QueryClientProvider>,
  )
  fireEvent.click(await screen.findByRole('checkbox', { name: /Look for free PDFs weekly/ }))
  await waitFor(() => expect(invalidate).toHaveBeenCalled())
  expect(invalidate.mock.calls.map(([f]) => f?.queryKey)).toEqual([['paper-sources']])
})
