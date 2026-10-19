// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, test, vi } from 'vitest'
import { AlreadyInLibraryError, NoFreePdfError, api } from '@/api/client'
import { GetPdfActions } from './GetPdfActions'

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  render(
    <QueryClientProvider client={client}>
      <GetPdfActions paperId="p1" title="Sleep and memory" />
    </QueryClientProvider>,
  )
  return invalidate
}

afterEach(() => vi.restoreAllMocks())

test('Upload PDF sends the file, then refreshes papers, the paper and the workspaces', async () => {
  const upload = vi.spyOn(api, 'uploadPaperPdf').mockResolvedValue({ id: 'p1' } as any)
  const invalidate = setup()
  const file = new File(['%PDF'], 'a.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('Upload PDF for Sleep and memory'), { target: { files: [file] } })
  await waitFor(() => expect(upload).toHaveBeenCalledWith('p1', file))
  await waitFor(() => {
    const keys = invalidate.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey))
    expect(keys).toEqual(expect.arrayContaining(['["papers"]', '["papers","p1"]', '["workspaces"]']))
  })
})

test('a refused upload reads in words', async () => {
  vi.spyOn(api, 'uploadPaperPdf').mockRejectedValue(new Error('not_a_pdf'))
  setup()
  const file = new File(['x'], 'a.txt', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('Upload PDF for Sleep and memory'), { target: { files: [file] } })
  expect(await screen.findByRole('alert')).toHaveTextContent('That file is not a PDF.')
})

test('Find free copy says it is looking, then refreshes on success', async () => {
  let done: (v: unknown) => void = () => {}
  const find = vi.spyOn(api, 'findPaperPdf').mockReturnValue(new Promise((r) => (done = r)) as any)
  const invalidate = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Find free copy' }))
  expect(await screen.findByText('Looking for a free copy…')).toBeInTheDocument()
  expect(find).toHaveBeenCalledWith('p1')
  done({ id: 'p1' })
  await waitFor(() => expect(invalidate).toHaveBeenCalled())
  await waitFor(() => expect(screen.queryByText('Looking for a free copy…')).toBeNull())
})

test('a failed find lists what was tried and where a copy may be', async () => {
  vi.spyOn(api, 'findPaperPdf').mockRejectedValue(
    new NoFreePdfError('x', [{ url: 'https://pub.example/a.pdf', outcome: 'http_403' }], ['https://repo.example/p']),
  )
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Find free copy' }))
  expect(await screen.findByText('No free copy was found.')).toBeInTheDocument()
  expect(screen.getByText(/pub\.example\/a\.pdf: the site answered 403/)).toBeInTheDocument()
  expect(screen.getByText('Where a copy may be:')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'https://repo.example/p' })).toHaveAttribute('href', 'https://repo.example/p')
})

test('a held arXiv copy links to the other paper', async () => {
  vi.spyOn(api, 'findPaperPdf').mockRejectedValue(new AlreadyInLibraryError('already_in_library', 'p2'))
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Find free copy' }))
  expect(await screen.findByText(/Your library already holds this work as another paper\./)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open it' }).getAttribute('href')).toContain('p2')
})

test('already_has_pdf reads in words', async () => {
  vi.spyOn(api, 'findPaperPdf').mockRejectedValue(new Error('already_has_pdf'))
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Find free copy' }))
  expect(await screen.findByText('This paper already has its PDF.')).toBeInTheDocument()
})
