// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { WorkspaceNotes } from './WorkspaceNotes'

const state = vi.hoisted(() => ({ notes: [] as unknown[] | undefined }))
vi.mock('@/api/queries', () => ({
  useWorkspaceNotes: () => ({ data: state.notes, error: null }),
  useWorkspacePapers: () => ({ data: [], error: null }),
}))

test('Export to Markdown is hidden with no notes', () => {
  state.notes = []
  render(<WorkspaceNotes workspaceId="w 1" />)
  expect(screen.getByText('No notes yet')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Export to Markdown' })).not.toBeInTheDocument()
})

test('while loading it shows a skeleton, not the empty copy', () => {
  state.notes = undefined
  render(<WorkspaceNotes workspaceId="w1" />)
  expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
  expect(screen.queryByText('No notes yet')).not.toBeInTheDocument()
})
