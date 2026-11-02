// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import type { Check, Note } from '@/api/client'
import { PASSES } from '@/features/reading/passes'
import { ExitTestRow } from './ExitTestRow'

let notes: Note[] = []
let checks: Check[] = []
vi.mock('@/api/queries', () => ({ useNotes: () => ({ data: notes }) }))
vi.mock('./queries', () => ({ usePaperChecks: () => ({ data: checks }) }))

const note = (over: Partial<Note> = {}) => ({ id: 'n1', kind: 'summary', provenance: 'human', created_at: '2026-10-01T00:00:00Z', ...over }) as Note
const check = (over: Partial<Check> = {}) => ({ note_id: 'n1', stale: false, created_at: '2026-10-05T12:00:00Z', lines: [], ...over }) as Check
const onWrite = vi.fn()
const onOpen = vi.fn()
const setup = () => render(<ExitTestRow paperId="p1" pass={PASSES[1]} onWrite={onWrite} onOpen={onOpen} />)

beforeEach(() => {
  notes = []
  checks = []
  onWrite.mockClear()
  onOpen.mockClear()
})

test('not written: says so and Write it passes the kind', () => {
  setup()
  expect(screen.getByText('Your summary: not written yet')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Write it' }))
  expect(onWrite).toHaveBeenCalledWith('summary')
})

test('not checked: Open passes the note id', () => {
  notes = [note()]
  setup()
  expect(screen.getByText('Your summary: not checked yet')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open' }))
  expect(onOpen).toHaveBeenCalledWith('n1')
})

test('changed since its check', () => {
  notes = [note()]
  checks = [check({ stale: true })]
  setup()
  expect(screen.getByText('Your summary: changed since its check')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument()
})

test('checked: counts the gaps', () => {
  notes = [note()]
  checks = [check({ lines: [{ verdict: 'missing', text: 'a' }, { verdict: 'unsupported', text: 'b' }] as Check['lines'] })]
  setup()
  expect(screen.getByText(/Your summary: checked .*: 1 missing, 1 unsupported/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument()
})

test('a newer AI note of the kind is not shown', () => {
  notes = [note(), note({ id: 'ai', provenance: 'llm', created_at: '2026-10-09T00:00:00Z' })]
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Open' }))
  expect(onOpen).toHaveBeenCalledWith('n1')
})
