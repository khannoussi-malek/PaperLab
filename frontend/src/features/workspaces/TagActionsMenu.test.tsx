// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { TagActionsMenu } from './TagActionsMenu'
import { tagSummary } from './tagFixtures'

function setup(opts: { renameError?: Error | null } = {}) {
  const rename = vi.fn((_v: unknown, o?: { onSuccess?: (r: { old: string; new: string }) => void }) => o?.onSuccess?.({ old: 'rct', new: 'trial' }))
  const del = vi.fn((_v: unknown, o?: { onSuccess?: () => void }) => o?.onSuccess?.())
  vi.spyOn(queries, 'useRenameTag').mockReturnValue({ mutate: rename, error: opts.renameError ?? null, reset: vi.fn() } as any)
  vi.spyOn(queries, 'useDeleteTag').mockReturnValue({ mutate: del, error: null, reset: vi.fn() } as any)
  const onRenamed = vi.fn()
  const onDeleted = vi.fn()
  render(<TagActionsMenu workspaceId="w1" tag={tagSummary('rct', 3)} onRenamed={onRenamed} onDeleted={onDeleted} />)
  return { rename, del, onRenamed, onDeleted }
}

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const open = async (item: string) => {
  fireEvent.keyDown(screen.getByRole('button', { name: 'Actions for tag rct' }), { key: 'Enter' })
  fireEvent.click(await screen.findByRole('menuitem', { name: item }))
}

test('rename saves the new name and reports old and new', async () => {
  const { rename, onRenamed } = setup()
  await open('Rename')
  expect(await screen.findByText('Rename tag')).toBeTruthy()
  const input = screen.getByRole('textbox') as HTMLInputElement
  expect(input.value).toBe('rct')
  fireEvent.change(input, { target: { value: 'trial' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(rename).toHaveBeenCalledWith({ tagId: 't-rct', newName: 'trial' }, expect.anything())
  expect(onRenamed).toHaveBeenCalledWith('rct', 'trial')
})

test('a rename that fails with tag_exists says so in plain words', async () => {
  setup({ renameError: new Error('tag_exists') })
  await open('Rename')
  expect(await screen.findByText('A tag with that name already exists.')).toBeTruthy()
})

test('delete asks first with the exact copy, then drops the tag', async () => {
  const { del, onDeleted } = setup()
  await open('Delete')
  expect(await screen.findByText('Delete tag "rct"?')).toBeTruthy()
  expect(screen.getByText('The tag is removed from 3 papers. No papers are deleted.')).toBeTruthy()
  expect(del).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(del).toHaveBeenCalledWith('t-rct', expect.anything()))
  expect(onDeleted).toHaveBeenCalledWith('rct')
})

test('delete can be cancelled', async () => {
  const { del } = setup()
  await open('Delete')
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))
  expect(del).not.toHaveBeenCalled()
})

test('closing the rename dialog with Escape puts focus back on the tag\'s actions button', async () => {
  setup()
  await open('Rename')
  fireEvent.keyDown(await screen.findByRole('textbox'), { key: 'Escape' })
  await waitFor(() => expect(screen.queryByText('Rename tag')).toBeNull())
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Actions for tag rct' })))
})
