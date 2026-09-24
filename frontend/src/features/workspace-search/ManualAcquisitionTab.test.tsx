// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { ManualAcquisitionTab } from './ManualAcquisitionTab'
import * as queries from '@/api/queries'
import { api } from '@/api/client'

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

beforeEach(() => {
  vi.spyOn(queries, 'useSearchHits').mockReturnValue({
    data: { pages: [{ items: [failedHit], next_cursor: null }] },
    hasNextPage: false,
    fetchNextPage: vi.fn(),
  } as any)
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
