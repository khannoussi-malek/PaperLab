// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { WorkspaceNotes } from './WorkspaceNotes'

const state = vi.hoisted(() => ({ notes: [] as unknown[] | undefined, error: null as Error | null, refetch: vi.fn() }))
vi.mock('@/api/queries', () => ({
  useWorkspaceNotes: () => ({ data: state.notes, error: state.error, refetch: state.refetch }),
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

test('a failed load shows the error and a Retry that refetches', () => {
  state.notes = undefined
  state.error = new Error('Could not load notes.')
  render(<WorkspaceNotes workspaceId="w1" />)
  expect(screen.getByRole('alert')).toHaveTextContent('Could not load notes.')
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(state.refetch).toHaveBeenCalled()
  state.error = null
})
