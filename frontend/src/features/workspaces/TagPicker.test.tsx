// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { TagPicker } from './TagPicker'
import { tagSummary } from './tagFixtures'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
Element.prototype.scrollIntoView = () => {}

type Opts = { mode?: 'add' | 'remove'; error?: Error | null; isPending?: boolean; paperTags?: Record<string, string[]> }
function setup({ mode = 'add', error = null, isPending = false, paperTags = { p1: ['rct'], p2: ['cohort'], p3: ['other'] } }: Opts = {}) {
  vi.spyOn(queries, 'useTags').mockReturnValue({ data: [tagSummary('rct', 2), tagSummary('cohort', 1), tagSummary('other', 1)] } as any)
  vi.spyOn(queries, 'usePaperTags').mockReturnValue({ data: paperTags } as any)
  const reset = vi.fn()
  const apply = vi.fn((_v: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.())
  const remove = vi.fn((_v: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.())
  vi.spyOn(queries, 'useApplyTag').mockReturnValue({ mutate: apply, error, isPending, reset } as any)
  vi.spyOn(queries, 'useRemoveTag').mockReturnValue({ mutate: remove, error, isPending, reset } as any)
  const onDone = vi.fn()
  render(<TagPicker workspaceId="w1" mode={mode} paperIds={['p1', 'p2']} onDone={onDone} />)
  return { apply, remove, onDone, reset }
}

afterEach(() => { cleanup(); vi.restoreAllMocks() })

test('add mode: choosing an existing tag applies it to every selected paper', () => {
  const { apply, onDone } = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Tag…' }))
  fireEvent.click(screen.getByRole('option', { name: /rct/ }))
  expect(apply).toHaveBeenCalledWith({ tag: 'rct', paperIds: ['p1', 'p2'] }, expect.anything())
  expect(onDone).toHaveBeenCalled()
})

test('add mode: a new name offers Create, a case-variant of an existing one does not', () => {
  const { apply } = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Tag…' }))
  const input = screen.getByRole('combobox', { name: 'Tag name' })
  fireEvent.change(input, { target: { value: '  Review ' } })
  fireEvent.click(screen.getByRole('option', { name: 'Create "Review"' }))
  expect(apply).toHaveBeenCalledWith({ tag: 'Review', paperIds: ['p1', 'p2'] }, expect.anything())
  fireEvent.click(screen.getByRole('button', { name: 'Tag…' }))
  fireEvent.change(screen.getByRole('combobox', { name: 'Tag name' }), { target: { value: 'RCT' } })
  expect(screen.queryByRole('option', { name: /Create/ })).toBeNull()
  fireEvent.click(screen.getByRole('option', { name: /rct/ }))
  expect(apply).toHaveBeenLastCalledWith({ tag: 'rct', paperIds: ['p1', 'p2'] }, expect.anything())
})

test('remove mode lists only the tags on the selected papers and removes the chosen one', () => {
  const { remove } = setup({ mode: 'remove' })
  fireEvent.click(screen.getByRole('button', { name: 'Remove tag…' }))
  expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['rct', 'cohort'])
  fireEvent.change(screen.getByRole('combobox', { name: 'Tag name' }), { target: { value: 'zzz' } })
  expect(screen.queryByRole('option', { name: /Create/ })).toBeNull()
  fireEvent.change(screen.getByRole('combobox', { name: 'Tag name' }), { target: { value: '' } })
  fireEvent.click(screen.getByRole('option', { name: /cohort/ }))
  expect(remove).toHaveBeenCalledWith({ tag: 'cohort', paperIds: ['p1', 'p2'] }, expect.anything())
})

test('a failed tagging shows the plain-words message', () => {
  setup({ error: new Error('invalid_tag_name') })
  fireEvent.click(screen.getByRole('button', { name: 'Tag…' }))
  expect(screen.getByText('Tag names are 1 to 64 characters.')).toBeTruthy()
})

test('the tags cannot be chosen again while one is being applied', () => {
  setup({ isPending: true })
  fireEvent.click(screen.getByRole('button', { name: 'Tag…' }))
  expect(screen.getAllByRole('option').every((o) => o.getAttribute('aria-disabled') === 'true')).toBe(true)
})

test('closing the picker clears a previous error', () => {
  const { reset } = setup({ error: new Error('tag_exists') })
  fireEvent.click(screen.getByRole('button', { name: 'Tag…' }))
  fireEvent.keyDown(screen.getByRole('combobox', { name: 'Tag name' }), { key: 'Escape' })
  expect(reset).toHaveBeenCalled()
})

test('remove mode says so when the selected papers carry no tags', () => {
  setup({ mode: 'remove', paperTags: {} })
  fireEvent.click(screen.getByRole('button', { name: 'Remove tag…' }))
  expect(screen.getByText('The selected papers have no tags.')).toBeTruthy()
})
