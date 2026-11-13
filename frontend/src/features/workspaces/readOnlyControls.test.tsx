// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import * as queries from '@/api/queries'
import { READ_ONLY_TEXT } from '@/lib/errorWords'
import { ReadOnlyContext } from './readOnlyContext'
import { TagPicker } from './TagPicker'
import { SavedSearches } from '../workspace-search/SavedSearches'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function wrap(readOnly: boolean, ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ReadOnlyContext.Provider value={readOnly}>{ui}</ReadOnlyContext.Provider>
    </QueryClientProvider>,
  )
}

function mockTagHooks() {
  vi.spyOn(queries, 'useTags').mockReturnValue({ data: [] } as any)
  vi.spyOn(queries, 'usePaperTags').mockReturnValue({ data: {} } as any)
  vi.spyOn(queries, 'useApplyTag').mockReturnValue({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false } as any)
  vi.spyOn(queries, 'useRemoveTag').mockReturnValue({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false } as any)
}

test('the tag button is disabled on a read-only workspace, with the words as its title', () => {
  mockTagHooks()
  wrap(true, <TagPicker workspaceId="w1" mode="add" paperIds={['p1']} onDone={() => {}} />)
  const button = screen.getByRole('button', { name: 'Tag…' })
  expect(button.hasAttribute('disabled')).toBe(true)
  expect(button.getAttribute('title')).toBe(READ_ONLY_TEXT)
})

test('the tag button stays enabled on an editable workspace', () => {
  mockTagHooks()
  wrap(false, <TagPicker workspaceId="w1" mode="add" paperIds={['p1']} onDone={() => {}} />)
  const button = screen.getByRole('button', { name: 'Tag…' })
  expect(button.hasAttribute('disabled')).toBe(false)
  expect(button.getAttribute('title')).toBeNull()
})

function mockSavedSearchHooks() {
  vi.spyOn(queries, 'useSavedSearches').mockReturnValue({ data: [], isPending: false, isError: false } as any)
  vi.spyOn(queries, 'useUpdateSavedSearch').mockReturnValue({ mutate: vi.fn(), error: null } as any)
  vi.spyOn(queries, 'useDeleteSavedSearch').mockReturnValue({ mutate: vi.fn(), error: null } as any)
  vi.spyOn(queries, 'useRunSavedSearchNow').mockReturnValue({ mutate: vi.fn(), isPending: false } as any)
}

test('saving a search is disabled on a read-only workspace', () => {
  mockSavedSearchHooks()
  wrap(true, <SavedSearches workspaceId="w1" currentQuery="" onRunStarted={() => {}} onShowNew={() => {}} />)
  const button = screen.getByRole('button', { name: 'Save this search…' })
  expect(button.hasAttribute('disabled')).toBe(true)
  expect(button.getAttribute('title')).toBe(READ_ONLY_TEXT)
})

test('saving a search stays enabled on an editable workspace', () => {
  mockSavedSearchHooks()
  wrap(false, <SavedSearches workspaceId="w1" currentQuery="" onRunStarted={() => {}} onShowNew={() => {}} />)
  expect(screen.getByRole('button', { name: 'Save this search…' }).hasAttribute('disabled')).toBe(false)
})
