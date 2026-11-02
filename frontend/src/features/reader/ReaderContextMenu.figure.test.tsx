// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ReaderContextMenu } from './ReaderContextMenu'

const noop = vi.fn()
const actions = { onClose: noop, onColorNote: noop, onEditNote: noop, onDeleteNote: noop, onHighlightDraft: noop, onAddNote: noop, onAddNumber: noop, onCancelDraft: noop, onCopy: noop }

test.each([
  [{ kind: 'draft', quote: 'Sleep helps' } as const, true],
  [{ kind: 'draft', quote: 'Figure on p. 4', figure: true } as const, false],
])('a draft menu offers number and copy only for text: %j', (target, offered) => {
  render(<ReaderContextMenu menu={{ x: 0, y: 0, target }} {...actions} />)
  expect(screen.getByRole('menuitem', { name: 'Add note…' })).toBeInTheDocument()
  expect(screen.queryByRole('menuitem', { name: 'Add as number…' }) !== null).toBe(offered)
  expect(screen.queryByRole('menuitem', { name: 'Copy text' }) !== null).toBe(offered)
})
