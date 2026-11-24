// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import type { Candidate } from '@/entities'
import { AlreadyInLibraryError, api } from '@/services/api'
import { useAddPublishedVersion, useCitationRequests, useDataRequests, useManuscriptRequests } from '@/services/queries'

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
afterEach(() => { vi.restoreAllMocks(); client.clear() })

test('the manuscript requests are bound to their manuscript and keep one identity across renders', async () => {
  const forward = vi.spyOn(api, 'syncForward').mockResolvedValue({ page: 2, x: 0, y: 10 })
  const save = vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue({} as never)
  const { result, rerender } = renderHook(({ id }) => useManuscriptRequests(id), { initialProps: { id: 'm1' } })
  const first = result.current
  await first.syncForward('main.tex', 4)
  await first.saveFile('main.tex', 'text', 'stamp')
  expect(forward).toHaveBeenCalledWith('m1', 'main.tex', 4)
  expect(save).toHaveBeenCalledWith('m1', 'main.tex', 'text', 'stamp')
  rerender({ id: 'm1' })
  expect(result.current).toBe(first) // effects that list it as a dependency don't run again
  rerender({ id: 'm2' })
  expect(result.current).not.toBe(first)
})

test("the capture dialogs' reads are one object for every render and every paper", async () => {
  const preview = vi.spyOn(api, 'previewTable').mockResolvedValue({} as never)
  const { result, rerender } = renderHook(() => useDataRequests())
  const first = result.current
  rerender()
  expect(result.current).toBe(first) // AddNumberDialog's effect runs again only for new text
  await first.previewTable('p1', 3, [0, 0, 1, 1])
  expect(preview).toHaveBeenCalledWith('p1', 3, [0, 0, 1, 1])
})

test('plain citations are read as APA text for the workspace', async () => {
  const text = vi.spyOn(api, 'citationsText').mockResolvedValue('A. (2020).')
  const { result } = renderHook(() => useCitationRequests('w1'))
  expect(await result.current.plainText()).toBe('A. (2020).')
  expect(text).toHaveBeenCalledWith('w1', 'apa')
})

const found = (fields: Partial<Candidate>) => ({ doi: '10.1/X', paper_id: null, pdf_urls: ['https://x/pdf'], ...fields }) as Candidate

test.each([
  ['nothing found', [], undefined, { kind: 'not-found' }],
  ['already in the library', [found({ paper_id: 'p9' })], undefined, { kind: 'owned', paperId: 'p9' }],
  ['no free PDF', [found({ pdf_urls: [] })], undefined, { kind: 'no-pdf' }],
  ['added', [found({})], undefined, { kind: 'added' }],
  ['added meanwhile (409)', [found({})], new AlreadyInLibraryError('taken', 'p7'), { kind: 'owned', paperId: 'p7' }],
])('the published version: %s', async (_name, results, addError, outcome) => {
  vi.spyOn(api, 'searchPapers').mockResolvedValue({ results, notices: [] } as never)
  vi.spyOn(api, 'addCandidate').mockImplementation(() => (addError ? Promise.reject(addError) : Promise.resolve({} as never)))
  const { result } = renderHook(() => useAddPublishedVersion('10.1/x'), { wrapper })
  result.current.mutate()
  await waitFor(() => expect(result.current.data).toEqual(outcome))
})
