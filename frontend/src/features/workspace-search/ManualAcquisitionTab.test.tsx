// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ManualAcquisitionTab } from './ManualAcquisitionTab'
import * as queries from '@/api/queries'
import { api } from '@/api/client'
import { copyText } from '@/lib/clipboard'
import { workspaceHref } from '@/lib/route'

vi.mock('@/lib/clipboard', () => ({ copyText: vi.fn() }))

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const failedHit = {
  id: 'h1',
  run_id: 'run-1',
  external_ref_id: null,
  source_method: 'arxiv',
  normalized_title: 'unreachable paper',
  first_seen_at: '2026-09-24T00:00:00Z',
  stage1_status: null,
  stage1_exclude_reason: null,
  stage1_note: null,
  priority: null,
  topic_fit: null,
  acquisition_status: 'failed',
  paper_id: null,
}

const richHit = {
  ...failedHit,
  id: 'h2',
  external_ref_id: 'ref-2',
  normalized_title: 'the lowercase title',
  title: 'The Real Title',
  authors: ['Ada Lovelace', 'Charles Babbage'],
  year: 1843,
  venue: 'Analytical Engine Quarterly',
  doi: '10.1234/real',
}

function mockHits(items: object[], overrides: Partial<Record<string, unknown>> = {}, awaiting: object[] = []) {
  vi.spyOn(queries, 'useSearchHits').mockImplementation(((_ws: string, _stage1?: string, status?: string) => ({
    data: { pages: [{ items: status === 'awaiting_pdf' ? awaiting : items, next_cursor: null }] },
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    ...(status === 'awaiting_pdf' ? {} : overrides),
  })) as any)
}

beforeEach(() => {
  mockHits([failedHit])
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('renders hits with acquisition_status failed, filtered via useSearchHits', () => {
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)

  expect(queries.useSearchHits).toHaveBeenCalledWith('ws-1', undefined, 'failed')
  expect(screen.getByText('unreachable paper')).toBeInTheDocument()
  expect(screen.getByLabelText('Upload PDF for unreachable paper')).toBeInTheDocument()
})

test('a hit with no linked ExternalRef falls back to normalized_title and shows no Open page/Copy DOI', () => {
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)

  expect(screen.getByText('unreachable paper')).toBeInTheDocument()
  expect(screen.queryByText('Open page')).not.toBeInTheDocument()
  expect(screen.queryByText('Copy DOI')).not.toBeInTheDocument()
})

test('a hit with an empty-string title (falsy but not null) still falls back to normalized_title, not a blank row', () => {
  mockHits([{ ...failedHit, external_ref_id: 'ref-3', title: '' }])
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)

  expect(screen.getByText('unreachable paper')).toBeInTheDocument()
})

test('a hit with a linked ExternalRef shows the real title, byline, an Open page link and a Copy DOI button (I7)', async () => {
  mockHits([richHit])
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)

  expect(screen.getByText('The Real Title')).toBeInTheDocument()
  expect(screen.queryByText('the lowercase title')).not.toBeInTheDocument()
  expect(screen.getByText('Ada Lovelace, Charles Babbage · 1843 · Analytical Engine Quarterly')).toBeInTheDocument()

  const openPage = screen.getByRole('link', { name: 'Open page' })
  expect(openPage).toHaveAttribute('href', 'https://doi.org/10.1234/real')

  fireEvent.click(screen.getByRole('button', { name: 'Copy DOI' }))
  await waitFor(() => expect(copyText).toHaveBeenCalledWith('10.1234/real'))
})

test('uploading a file calls the upload endpoint for that hit', async () => {
  const uploadSpy = vi.spyOn(api, 'uploadHitPdf').mockResolvedValue({} as any)

  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)

  const file = new File([new Uint8Array([1, 2, 3])], 'paper.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('Upload PDF for unreachable paper'), { target: { files: [file] } })

  await waitFor(() => expect(uploadSpy).toHaveBeenCalledWith('ws-1', 'h1', file))
})

test('a failed upload shows an alert with the error', async () => {
  vi.spyOn(api, 'uploadHitPdf').mockRejectedValue(new Error('Upload failed'))

  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)

  const file = new File([new Uint8Array([1, 2, 3])], 'paper.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('Upload PDF for unreachable paper'), { target: { files: [file] } })

  expect(await screen.findByRole('alert')).toHaveTextContent('Upload failed')
})

test('file input is disabled while upload is pending', async () => {
  vi.spyOn(api, 'uploadHitPdf').mockImplementation(
    () => new Promise(() => {}) // never resolves, keeps mutation pending
  )

  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)

  const input = screen.getByLabelText('Upload PDF for unreachable paper') as HTMLInputElement
  expect(input.disabled).toBe(false)

  const file = new File([new Uint8Array([1, 2, 3])], 'paper.pdf', { type: 'application/pdf' })
  fireEvent.change(input, { target: { files: [file] } })

  await waitFor(() => expect(input.disabled).toBe(true))
})

test('hides Load more when there is no next page (the common case)', () => {
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  expect(screen.queryByRole('button', { name: /Load more/ })).not.toBeInTheDocument()
})

test('Load more fetches the next page when there are over 50 failures (I7 fix 1)', () => {
  const fetchNextPage = vi.fn()
  mockHits([failedHit], { hasNextPage: true, fetchNextPage })
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)

  const loadMore = screen.getByRole('button', { name: 'Load more' })
  fireEvent.click(loadMore)

  expect(fetchNextPage).toHaveBeenCalledTimes(1)
})

test('Load more is disabled (and relabelled) while a page is already fetching', () => {
  mockHits([failedHit], { hasNextPage: true, isFetchingNextPage: true })
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)

  expect(screen.getByRole('button', { name: 'Loading…' })).toBeDisabled()
})

test('while loading it shows a skeleton, not the empty copy', () => {
  mockHits([], { data: undefined, isPending: true })
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
  expect(screen.queryByText('Nothing to fetch by hand')).not.toBeInTheDocument()
})

test('when empty it says so', () => {
  mockHits([])
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  expect(screen.getByRole('heading', { name: 'Nothing to fetch by hand' })).toBeInTheDocument()
  expect(screen.getByText('Relevant papers land here only when no free PDF was found for them.')).toBeInTheDocument()
  expect(workspaceHref('ws-1', 'search')).toContain('tab=search')
})

test('a failed query shows the error and Retry, not the empty copy', () => {
  const refetch = vi.fn()
  mockHits([], { data: undefined, isPending: false, isError: true, error: new Error('Nope.'), refetch })
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(refetch).toHaveBeenCalled()
  expect(screen.queryByText('Nothing to fetch by hand')).not.toBeInTheDocument()
})

test('Get PDFs says how many and why', () => {
  mockHits([failedHit, richHit])
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  expect(screen.getByRole('heading', { name: '2 relevant papers need a PDF' })).toBeInTheDocument()
  expect(screen.getByText('Relevant papers land here only when no free PDF was found for them.')).toBeInTheDocument()
})

test('the upload button picks a file and shows its name', async () => {
  const uploadSpy = vi.spyOn(api, 'uploadHitPdf').mockResolvedValue({} as any)
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  const file = new File([new Uint8Array([1, 2, 3])], 'paper.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('Upload PDF for unreachable paper'), { target: { files: [file] } })
  expect(screen.getByRole('button', { name: /paper\.pdf/ })).toBeInTheDocument()
  await waitFor(() => expect(uploadSpy).toHaveBeenCalledWith('ws-1', 'h1', file))
})

test('with another page the heading says "At least N"', () => {
  mockHits([failedHit, richHit], { hasNextPage: true })
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  expect(screen.getByRole('heading', { name: 'At least 2 relevant papers need a PDF' })).toBeInTheDocument()
})

test('the hidden input is out of the tab order; the visible button names the paper', () => {
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  expect(screen.getByLabelText('Upload PDF for unreachable paper')).toHaveAttribute('tabindex', '-1')
  expect(screen.getByRole('button', { name: 'Upload PDF for unreachable paper' })).toBeInTheDocument()
})

test('after a pick the button shows the file name and still names the paper', () => {
  vi.spyOn(api, 'uploadHitPdf').mockImplementation(() => new Promise(() => {}))
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  const file = new File([new Uint8Array([1])], 'paper.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('Upload PDF for unreachable paper'), { target: { files: [file] } })
  expect(screen.getByRole('button', { name: 'paper.pdf for unreachable paper' })).toBeInTheDocument()
})

test('a failed upload clears the shown file name', async () => {
  vi.spyOn(api, 'uploadHitPdf').mockRejectedValue(new Error('Upload failed'))
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  const file = new File([new Uint8Array([1])], 'paper.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('Upload PDF for unreachable paper'), { target: { files: [file] } })
  await screen.findByRole('alert')
  expect(screen.getByRole('button', { name: 'Upload PDF for unreachable paper' })).toBeInTheDocument()
})

test('an already_has_pdf refusal is said in words', async () => {
  vi.spyOn(api, 'uploadHitPdf').mockRejectedValue(new Error('already_has_pdf'))
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  const file = new File(['%PDF'], 'a.pdf', { type: 'application/pdf' })
  fireEvent.change(await screen.findByLabelText('Upload PDF for unreachable paper'), { target: { files: [file] } })
  expect(await screen.findByRole('alert')).toHaveTextContent('This paper already has its PDF.')
})

const awaitingHit = { ...failedHit, id: 'h9', normalized_title: 'saved without pdf', acquisition_status: 'awaiting_pdf', paper_id: 'p9' }

test('lists papers saved without a PDF beside the failed ones, with Upload PDF through the hit route', async () => {
  mockHits([failedHit], {}, [awaitingHit])
  const upload = vi.spyOn(api, 'uploadHitPdf').mockResolvedValue({ ...awaitingHit, acquisition_status: 'manual' } as any)
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  expect(await screen.findByText('Saved without a PDF')).toBeInTheDocument()
  expect(screen.getByText('saved without pdf')).toBeInTheDocument()
  expect(screen.getByText('unreachable paper')).toBeInTheDocument()
  const file = new File(['%PDF'], 'a.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('Upload PDF for saved without pdf'), { target: { files: [file] } })
  await waitFor(() => expect(upload).toHaveBeenCalledWith('ws-1', 'h9', file))
})

test('Find free copy on a saved-without-PDF row uses the paper route; a failed hit has none', async () => {
  mockHits([failedHit], {}, [awaitingHit])
  const find = vi.spyOn(api, 'findPaperPdf').mockResolvedValue({ id: 'p9' } as any)
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  const buttons = await screen.findAllByRole('button', { name: /Find free copy/ })
  expect(buttons).toHaveLength(1)
  fireEvent.click(buttons[0])
  await waitFor(() => expect(find).toHaveBeenCalledWith('p9'))
})

test('a failed awaiting query shows the load error with a retry', () => {
  const refetch = vi.fn()
  vi.spyOn(queries, 'useSearchHits').mockImplementation(((_w: string, _s?: string, status?: string) =>
    status === 'awaiting_pdf'
      ? { data: undefined, isError: true, error: new Error('Awaiting broke.'), refetch, hasNextPage: false }
      : { data: { pages: [{ items: [failedHit], next_cursor: null }] }, hasNextPage: false }) as any)
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  expect(screen.getByText('Awaiting broke.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(refetch).toHaveBeenCalled()
})

test('saved-without-a-PDF rows are their own group, after the failed ones', () => {
  mockHits([failedHit], {}, [awaitingHit])
  renderWithClient(<ManualAcquisitionTab workspaceId="ws-1" />)
  const group = screen.getByRole('region', { name: 'Saved without a PDF' })
  expect(group).toHaveTextContent('saved without pdf')
  expect(group).not.toHaveTextContent('unreachable paper')
})

test('an upload through the hit route also refreshes the library and the paper', async () => {
  mockHits([failedHit], {}, [awaitingHit])
  vi.spyOn(api, 'uploadHitPdf').mockResolvedValue({ ...awaitingHit, acquisition_status: 'manual' } as any)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  render(<QueryClientProvider client={client}><ManualAcquisitionTab workspaceId="ws-1" /></QueryClientProvider>)
  const file = new File(['%PDF'], 'a.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('Upload PDF for saved without pdf'), { target: { files: [file] } })
  await waitFor(() => {
    const keys = invalidate.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey))
    expect(keys).toEqual(expect.arrayContaining(['["papers"]', '["papers","p9"]']))
  })
})
