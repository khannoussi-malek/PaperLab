// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { TagFilterMenu } from './TagFilterMenu'
import { tagSummary } from './tagFixtures'

// cmdk measures its list with these, and jsdom has neither.
vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
Element.prototype.scrollIntoView = () => {}

function setup(selected: string[] = [], match: 'any' | 'all' = 'any') {
  vi.spyOn(queries, 'useTags').mockReturnValue({ data: [tagSummary('rct', 3), tagSummary('cohort', 1)] } as any)
  const onChange = vi.fn()
  render(<TagFilterMenu workspaceId="w1" selected={selected} match={match} onChange={onChange} />)
  return onChange
}

afterEach(() => { cleanup(); vi.restoreAllMocks() })

test('is hidden on wide screens and shows how many tags are selected', () => {
  setup(['rct'])
  const trigger = screen.getByRole('button', { name: /Tags/ })
  expect(trigger.textContent).toContain('1')
  expect(trigger.closest('div')?.className).toContain('lg:hidden')
})

test('choosing a tag in the list adds it; choosing a selected one drops it', () => {
  const onChange = setup(['cohort'])
  fireEvent.click(screen.getByRole('button', { name: /Tags/ }))
  fireEvent.click(screen.getByRole('option', { name: /rct/ }))
  expect(onChange).toHaveBeenCalledWith(['cohort', 'rct'], 'any')
  fireEvent.click(screen.getByRole('option', { name: /cohort/ }))
  expect(onChange).toHaveBeenLastCalledWith([], 'any')
})

test('selected items say so and names read name and count apart', () => {
  setup(['cohort'])
  fireEvent.click(screen.getByRole('button', { name: /Tags/ }))
  expect(screen.getByRole('option', { name: 'cohort, 1 paper' }).getAttribute('aria-checked')).toBe('true')
  expect(screen.getByRole('option', { name: 'rct, 3 papers' }).getAttribute('aria-checked')).toBe('false')
})

test('has the Match all switch too', () => {
  const onChange = setup(['rct'])
  fireEvent.click(screen.getByRole('button', { name: /Tags/ }))
  fireEvent.click(screen.getByRole('switch', { name: 'Match all' }))
  expect(onChange).toHaveBeenCalledWith(['rct'], 'all')
})
