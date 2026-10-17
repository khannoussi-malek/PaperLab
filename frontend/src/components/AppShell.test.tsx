// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { AppShell } from './AppShell'

vi.mock('@/features/workspaces/WorkspaceSidebar', () => ({ WorkspaceSidebar: () => null }))
vi.mock('@/components/mode-toggle', () => ({ ModeToggle: () => null }))

afterEach(cleanup)

test('the rail column is hidden below md and the menu button opens it', () => {
  const { container } = render(<AppShell title="T">x</AppShell>)
  const grid = container.firstElementChild as HTMLElement
  expect(grid.className).toContain('grid-cols-1')
  expect(grid.className).toContain('md:grid-cols-[14rem_minmax(0,1fr)]')
  expect(container.querySelector('.hidden.md\\:flex')).toBeTruthy()
  expect(screen.queryByRole('dialog')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
  const dialog = screen.getByRole('dialog', { name: 'Navigation' })
  expect(within(dialog).getByRole('navigation', { name: 'Views' })).toBeTruthy()
})

test('choosing a view closes the drawer', () => {
  render(<AppShell title="T">x</AppShell>)
  fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('link', { name: 'Graph' }))
  expect(screen.queryByRole('dialog')).toBeNull()
})
