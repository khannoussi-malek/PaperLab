// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { TagSidebar } from './TagSidebar'
import { tagSummary } from './tagFixtures'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

const tags = [
  tagSummary('rct', 3, { peer_reviewed: 2, preprint: 1, unknown_review: 0, full_text: 2, abstract: 1, metadata: 0 }),
  tagSummary('cohort', 1),
]

function setup(selected: string[] = [], match: 'any' | 'all' = 'any', data = tags) {
  vi.spyOn(queries, 'useTags').mockReturnValue({ data } as any)
  const onChange = vi.fn()
  render(<TagSidebar workspaceId="w1" selected={selected} match={match} onChange={onChange} />)
  return onChange
}

afterEach(() => { cleanup(); vi.restoreAllMocks() })

test('lists each tag with its count as a toggle, and is only shown on wide screens', () => {
  setup(['cohort'])
  expect(screen.getByRole('heading', { name: 'Tags' })).toBeTruthy()
  const rct = screen.getByRole('button', { name: /rct/ })
  expect(rct.textContent).toContain('3')
  expect(rct.getAttribute('aria-pressed')).toBe('false')
  expect(screen.getByRole('button', { name: /cohort/ }).getAttribute('aria-pressed')).toBe('true')
  const aside = screen.getByRole('heading', { name: 'Tags' }).closest('aside')
  expect(aside?.classList.contains('hidden') && aside.classList.contains('lg:block')).toBe(true)
})

test('clicking a tag adds it to the selection, clicking a selected one drops it', () => {
  const onChange = setup(['cohort'])
  fireEvent.click(screen.getByRole('button', { name: /rct/ }))
  expect(onChange).toHaveBeenCalledWith(['cohort', 'rct'], 'any')
  fireEvent.click(screen.getByRole('button', { name: /cohort/ }))
  expect(onChange).toHaveBeenLastCalledWith([], 'any')
})

test('the tooltip gives the exact coverage line', async () => {
  setup()
  fireEvent.focus(screen.getByRole('button', { name: /rct/ }))
  const text = '3 papers · 2 peer-reviewed, 1 preprints, 0 unknown · 2 full text, 1 abstract only, 0 metadata only'
  expect((await screen.findAllByText(text)).length).toBeGreaterThan(0)
})

test('"Match all" flips match and keeps the tags', () => {
  const onChange = setup(['rct'])
  fireEvent.click(screen.getByRole('switch', { name: 'Match all' }))
  expect(onChange).toHaveBeenCalledWith(['rct'], 'all')
})

test('"Match all" is on when match is all, and turns it back to any', () => {
  const onChange = setup(['rct'], 'all')
  const sw = screen.getByRole('switch', { name: 'Match all' })
  expect(sw.getAttribute('aria-checked')).toBe('true')
  fireEvent.click(sw)
  expect(onChange).toHaveBeenCalledWith(['rct'], 'any')
})

test('no tags says how to make one', () => {
  setup([], 'any', [])
  expect(screen.getByText('No tags yet. Select papers and choose Tag… to add one.')).toBeTruthy()
})
