// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
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
  vi.spyOn(queries, 'useRenameTag').mockReturnValue({ mutate: vi.fn(), reset: vi.fn() } as any)
  vi.spyOn(queries, 'useDeleteTag').mockReturnValue({ mutate: vi.fn(), reset: vi.fn() } as any)
  const onChange = vi.fn()
  render(<TagSidebar workspaceId="w1" selected={selected} match={match} onChange={onChange} />)
  return onChange
}

afterEach(() => { cleanup(); vi.restoreAllMocks() })

test('lists each tag with its count as a toggle, and is only shown on wide screens', () => {
  setup(['cohort'])
  expect(screen.getByRole('heading', { name: 'Tags' })).toBeTruthy()
  const rct = screen.getByRole('button', { name: 'rct, 3 papers' })
  expect(rct.textContent).toContain('3')
  expect(rct.getAttribute('aria-pressed')).toBe('false')
  expect(screen.getByRole('button', { name: 'cohort, 1 paper' }).getAttribute('aria-pressed')).toBe('true')
  const aside = screen.getByRole('heading', { name: 'Tags' }).closest('aside')
  expect(aside?.classList.contains('hidden') && aside.classList.contains('lg:block')).toBe(true)
})

test('clicking a tag adds it to the selection, clicking a selected one drops it', () => {
  const onChange = setup(['cohort'])
  fireEvent.click(screen.getByRole('button', { name: /^rct,/ }))
  expect(onChange).toHaveBeenCalledWith(['cohort', 'rct'], 'any')
  fireEvent.click(screen.getByRole('button', { name: /^cohort,/ }))
  expect(onChange).toHaveBeenLastCalledWith([], 'any')
})

test('the tooltip gives the exact coverage line', async () => {
  setup()
  fireEvent.focus(screen.getByRole('button', { name: /^rct,/ }))
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

test('each tag has its own actions button, beside the toggle and not inside it', () => {
  setup()
  const actions = screen.getByRole('button', { name: 'Actions for tag rct' })
  expect(screen.getByRole('button', { name: 'rct, 3 papers' }).contains(actions)).toBe(false)
  expect(screen.getByRole('button', { name: 'Actions for tag cohort' })).toBeTruthy()
})

test('renaming a selected tag swaps it in the filter; deleting drops it', async () => {
  const onChange = setup(['rct', 'cohort'])
  vi.spyOn(queries, 'useRenameTag').mockReturnValue({ mutate: (_v: unknown, o: any) => o.onSuccess({ old: 'rct', new: 'trial' }), reset: vi.fn() } as any)
  vi.spyOn(queries, 'useDeleteTag').mockReturnValue({ mutate: (_v: unknown, o: any) => o.onSuccess(), reset: vi.fn() } as any)
  cleanup()
  render(<TagSidebar workspaceId="w1" selected={['rct', 'cohort']} match="any" onChange={onChange} />)
  fireEvent.keyDown(screen.getByRole('button', { name: 'Actions for tag rct' }), { key: 'Enter' })
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Save' }))
  expect(onChange).toHaveBeenLastCalledWith(['trial', 'cohort'], 'any')
  fireEvent.keyDown(screen.getByRole('button', { name: 'Actions for tag cohort' }), { key: 'Enter' })
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
  expect(onChange).toHaveBeenLastCalledWith(['rct'], 'any')
})

test('the coverage line says "1 paper", not "1 papers"', async () => {
  setup()
  fireEvent.focus(screen.getByRole('button', { name: /^cohort,/ }))
  expect((await screen.findAllByText(/^1 paper · /)).length).toBeGreaterThan(0)
})

test('deleting a tag moves focus to the Tags heading instead of dropping it to the page', async () => {
  const del = vi.fn((_v: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.())
  setup()
  vi.spyOn(queries, 'useDeleteTag').mockReturnValue({ mutate: del, reset: vi.fn() } as any)
  cleanup()
  render(<TagSidebar workspaceId="w1" selected={[]} match="any" onChange={vi.fn()} />)
  fireEvent.keyDown(screen.getByRole('button', { name: 'Actions for tag rct' }), { key: 'Enter' })
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Tags' })))
})
