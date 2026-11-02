// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, beforeEach, expect, test, vi } from 'vitest'
import type { Check, Note } from '@/api/client'
import { NoteCheck } from './NoteCheck'

const run = vi.fn()
const cancelConfirm = vi.fn()
let stream: Record<string, unknown>
let checks: Check[] = []
vi.mock('./useCheckStream', () => ({ useCheckStream: () => ({ stream, run, cancelConfirm }) }))
vi.mock('./queries', () => ({ usePaperChecks: () => ({ data: checks }) }))
vi.mock('@/features/settings/DownloadSearchModel', () => ({ DownloadSearchModel: () => <div>download-model</div> }))
vi.mock('@/api/queries', () => ({ useReindexPaper: () => ({ mutate: vi.fn(), isPending: false, isSuccess: false, error: null }), useEmbeddingStatus: () => ({ data: undefined }) }))

const note = (over: Partial<Note> = {}) => ({ id: 'n1', kind: 'summary', provenance: 'human', ...over }) as Note
const idle = { status: 'idle', host: null, sources: null, lines: [], problem: null }
const props = { paperId: 'p1', onCite: vi.fn() }

beforeAll(() => {
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver
})

beforeEach(() => {
  stream = idle
  checks = []
  run.mockClear()
  cancelConfirm.mockClear()
})

test('renders nothing for a plain or assumption note', () => {
  const { container, rerender } = render(<NoteCheck {...props} note={note({ kind: null })} />)
  expect(container).toBeEmptyDOMElement()
  rerender(<NoteCheck {...props} note={note({ kind: 'assumption' })} />)
  expect(container).toBeEmptyDOMElement()
})

test('a human exit-test note offers Check against the paper', () => {
  render(<NoteCheck {...props} note={note()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check against the paper' }))
  expect(run).toHaveBeenCalledWith()
})

test.each(['llm', 'llm_edited'] as const)('a %s note is disabled with its tooltip', async (provenance) => {
  render(<NoteCheck {...props} note={note({ provenance })} />)
  expect(screen.getByRole('button', { name: 'Check against the paper' })).toBeDisabled()
  const wrapper = screen.getByRole('button', { name: 'Check against the paper' }).parentElement!
  expect(wrapper).toHaveAttribute('tabindex', '0')
  fireEvent.focus(wrapper)
  expect(await screen.findAllByText('Only text you wrote can be checked. This note came from AI.')).not.toHaveLength(0)
})

test('streaming: reading, then checking with kept lines', () => {
  stream = { ...idle, status: 'sources' }
  const { rerender } = render(<NoteCheck {...props} note={note()} />)
  expect(screen.getByRole('status')).toHaveTextContent('Reading the paper…')
  stream = { ...idle, status: 'streaming', sources: [], lines: [{ verdict: 'missing', text: 'No loss named.' }] }
  rerender(<NoteCheck {...props} note={note()} />)
  expect(screen.getByRole('status')).toHaveTextContent('Checking your summary…')
  expect(screen.getByText('No loss named.')).toBeInTheDocument()
})

test('a saved check shows its block', () => {
  checks = [{ note_id: 'n1', lines: [{ verdict: 'missing', text: 'Gap.' }], dropped: 0, sources: [], whole_paper: true, model: 'qwen', connection_name: null, prompt_version: 2, created_at: '2026-11-01T00:00:00Z', stale: false } as unknown as Check]
  render(<NoteCheck {...props} note={note()} />)
  expect(screen.getByRole('region', { name: 'Check of your summary' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
  expect(run).toHaveBeenCalled()
})

test('a refusal shows its text and Retry', () => {
  stream = { ...idle, status: 'error', problem: { message: 'Write your answers first.', retryable: true, reindex: false } }
  render(<NoteCheck {...props} note={note()} />)
  expect(screen.getByText('Write your answers first.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(run).toHaveBeenCalled()
})

test('search_not_set_up shows DownloadSearchModel', () => {
  stream = { ...idle, status: 'error', problem: { message: 'Search is not set up.', retryable: false, reindex: false, download: true } }
  render(<NoteCheck {...props} note={note()} />)
  expect(screen.getByText('download-model')).toBeInTheDocument()
})

test('a remote host asks first: Send runs it with confirm, Cancel does not', () => {
  stream = { ...idle, status: 'confirm', host: 'api.example.com' }
  render(<NoteCheck {...props} note={note()} />)
  expect(screen.getAllByText('Your note will be sent to api.example.com and may cost money. Send it?')).not.toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(cancelConfirm).toHaveBeenCalled()
  expect(run).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
  expect(run).toHaveBeenCalledWith(true)
})

test('editing the note after a finished check drops the finished stream, so the saved check shows as out of date', () => {
  stream = { ...idle, status: 'done', sources: [], lines: [{ verdict: 'missing', text: 'Gap.' }] }
  const { rerender } = render(<NoteCheck {...props} note={note({ body: 'first' })} />)
  cancelConfirm.mockClear() // mounting runs the effect once
  rerender(<NoteCheck {...props} note={note({ body: 'first' })} />)
  expect(cancelConfirm).not.toHaveBeenCalled()
  rerender(<NoteCheck {...props} note={note({ body: 'second' })} />)
  expect(cancelConfirm).toHaveBeenCalledTimes(1)
})
