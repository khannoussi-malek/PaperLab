// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'
import { EmptyState, GoToSearchAction, TabSkeleton } from './TabStates'

afterEach(cleanup)

test('the skeleton is a busy status with a screen-reader label and one bar per row', () => {
  const { container } = render(<TabSkeleton label="Loading papers to fetch" rows={4} />)
  const status = screen.getByRole('status')
  expect(status).toHaveAttribute('aria-busy', 'true')
  expect(status).toHaveTextContent('Loading papers to fetch')
  expect(container.querySelectorAll('[data-skeleton-row]')).toHaveLength(4)
})

test('the empty state has an h2 title, its sentence and its action', () => {
  render(<EmptyState title="Nothing yet" action={<a href="#x">Go</a>}>Do this next.</EmptyState>)
  expect(screen.getByRole('heading', { level: 2, name: 'Nothing yet' })).toBeInTheDocument()
  expect(screen.getByText('Do this next.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Go' })).toBeInTheDocument()
})

test('the step-1 action keeps the active run in the link', () => {
  render(<GoToSearchAction workspaceId="w1" runId="r1" />)
  expect(screen.getByRole('link', { name: 'Go to 1 · Search & screen' }).getAttribute('href')).toContain('run=r1')
})

test('the step-1 action links to the workspace search tab', () => {
  render(<GoToSearchAction workspaceId="w1" />)
  expect(screen.getByRole('link', { name: 'Go to 1 · Search & screen' })).toHaveAttribute('href', '#/workspaces/w1?tab=search')
})
