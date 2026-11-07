// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PersistentRail, RailSlot } from './PersistentRail'

vi.mock('@/features/workspaces/WorkspaceSidebar', () => ({ WorkspaceSidebar: () => null }))
afterEach(() => {
  window.location.hash = ''
})

// Two "pages", each drawing its own shell with a sidebar slot, as every view does.
function Library() {
  return <section aria-label="Library page"><RailSlot /></section>
}
function Graph() {
  return <section aria-label="Graph page"><RailSlot /></section>
}

describe('the persistent sidebar', () => {
  it('is one sidebar for the whole app, moved into each page\'s slot rather than drawn again', () => {
    window.location.hash = '#/'
    const { rerender } = render(<><Library /><PersistentRail /></>)
    const nav = screen.getByRole('navigation', { name: 'Views' })
    expect(screen.getByRole('region', { name: 'Library page' })).toContainElement(nav)

    rerender(<><Graph /><PersistentRail /></>)
    const after = screen.getByRole('navigation', { name: 'Views' })
    expect(after).toBe(nav)
    expect(screen.getByRole('region', { name: 'Graph page' })).toContainElement(after)
  })

  it('steps out of the page cross-fade (its own view-transition name), so only the live sidebar shows while its pill glides', () => {
    window.location.hash = '#/'
    render(<><Library /><PersistentRail /></>)
    expect(screen.getByRole('navigation', { name: 'Views' }).parentElement).toHaveClass('app-rail')
  })

  it('stays out of the page while no shell shows it (the reader, first-run setup)', () => {
    render(<><section aria-label="Reader" /><PersistentRail /></>)
    expect(screen.queryByRole('navigation', { name: 'Views' })).toBeNull()
  })
})
