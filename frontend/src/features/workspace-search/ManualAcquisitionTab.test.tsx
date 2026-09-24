// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ManualAcquisitionTab } from './ManualAcquisitionTab'
import * as queries from '@/api/queries'
import { api } from '@/api/client'
import { copyText } from '@/lib/clipboard'

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

function mockHits(items: object[], overrides: Partial<Record<string, unknown>> = {}) {
  vi.spyOn(queries, 'useSearchHits').mockReturnValue({
    data: { pages: [{ items, next_cursor: null }] },
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
    ...overrides,
  } as any)
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
