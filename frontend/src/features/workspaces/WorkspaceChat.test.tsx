// @vitest-environment jsdom
import { render } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import type { ChatSource, Workspace } from '@/api/client'
import { WorkspaceChat } from './WorkspaceChat'

const cite = vi.hoisted(() => ({ onCite: null as null | ((source: ChatSource) => void) }))
vi.mock('@/features/chat/ChatPanel', () => ({
  ChatPanel: ({ onCite }: { onCite: (source: ChatSource) => void }) => {
    cite.onCite = onCite
    return null
  },
}))
vi.mock('@/api/queries', () => ({ usePapers: () => ({ data: [] }), useWorkspacePapers: () => ({ data: [] }) }))
afterEach(() => { window.location.hash = '' })

const PAPER = '6f1c2a40-1111-4a8e-9c4e-000000000001'
const CHUNK = '6f1c2a40-2222-4a8e-9c4e-000000000002'
const workspace = { id: 'w1', paper_count: 1, note_count: 0 } as Workspace

test('a cited abstract opens its paper, never a page-0 jump', () => {
  render(<WorkspaceChat workspace={workspace} onShowNotes={vi.fn()} />)
  cite.onCite!({ label: 'C1', chunk_id: CHUNK, paper_id: PAPER, page: 0, section: 'Abstract', bbox: [], from_abstract: true })
  expect(window.location.hash).toBe(`#/papers/${PAPER}`)
})

test('a cited passage of a PDF still jumps to its page', () => {
  render(<WorkspaceChat workspace={workspace} onShowNotes={vi.fn()} />)
  cite.onCite!({ label: 'C1', chunk_id: CHUNK, paper_id: PAPER, page: 3, section: null, bbox: [], from_abstract: false })
  expect(window.location.hash).toBe(`#/papers/${PAPER}?chunk=${CHUNK}&page=3`)
})
