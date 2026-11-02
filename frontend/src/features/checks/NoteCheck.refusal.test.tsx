// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, expect, test, vi } from 'vitest'
import { api, type Check, type Note } from '@/api/client'
import { NoteCheck } from './NoteCheck'

// The real useCheckStream: NoteCheck.test.tsx mocks it, which hid a refusal that left no way to check again.
let checks: Check[] = []
vi.mock('./queries', () => ({ usePaperChecks: () => ({ data: checks }), useInvalidateChecks: () => vi.fn() }))
vi.mock('@/features/settings/DownloadSearchModel', () => ({ DownloadSearchModel: () => <div>download-model</div> }))
vi.mock('@/api/queries', () => ({
  useChatModels: () => ({ data: [{ id: 'm1', is_default: true }] }),
  useReindexPaper: () => ({ mutate: vi.fn(), isPending: false, isSuccess: false, error: null }),
  useEmbeddingStatus: () => ({ data: undefined }),
}))

const note = (body: string) => ({ id: 'n1', kind: 'five_cs', provenance: 'human', body }) as Note
const props = { paperId: 'p1', onCite: vi.fn() }
const refuse = (detail: string) => vi.spyOn(api, 'checkNote').mockImplementation(() => Promise.resolve(Response.json({ detail }, { status: 409 })))
const saved = { note_id: 'n1', lines: [{ verdict: 'missing', text: 'Gap. [C1]', cited: [1] }], dropped: 0, sources: [], whole_paper: true, model: 'q', connection_name: null, prompt_version: 2, created_at: '2026-11-01T00:00:00Z', stale: true } as unknown as Check

beforeAll(() => {
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver
})
afterEach(() => {
  checks = []
  vi.restoreAllMocks()
})

test('a refusal leaves a way to check again, and editing the note clears it', async () => {
  const spy = refuse('nothing_written')
  const { rerender } = render(<NoteCheck {...props} note={note('Category:')} />)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Check against the paper' })))
  expect(screen.getByText('Write your answers first: this note has only its headings.')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /Check/ }).length).toBe(1)
  rerender(<NoteCheck {...props} note={note('Category: a survey')} />)
  expect(screen.queryByText(/Write your answers first/)).not.toBeInTheDocument()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Check against the paper' })))
  expect(spy).toHaveBeenCalledTimes(2)
})

test('a saved check stays visible during a refusal, with one Check again and no Retry beside it', async () => {
  checks = [saved]
  vi.spyOn(api, 'checkNote').mockImplementation(() => Promise.resolve(Response.json({ detail: 'lens_empty' }, { status: 409 })))
  render(<NoteCheck {...props} note={note('x')} />)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Check again' })))
  expect(screen.getByText('Gap. [C1]')).toBeInTheDocument()
  expect(screen.getByText(/no sections/)).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /Check again|Retry/ })).toHaveLength(1)
})
