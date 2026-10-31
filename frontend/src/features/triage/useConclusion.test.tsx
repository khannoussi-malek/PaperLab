// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, type Chunk, type Section } from '@/api/client'
import { prefetchPaperSections } from '@/features/lenses/queries'
import { useConclusion } from './useConclusion'

afterEach(() => vi.restoreAllMocks())

const sec = (role: Section['role'], ids: string[], page = 9): Section =>
  ({ title: role, role, source: 'keyword', chunk_ids: ids, first_chunk_id: ids[0], page, preview: '' }) as Section
const chunk = (id: string, text: string, ordinal = 0): Chunk => ({ id, text, ordinal, page: 9 }) as unknown as Chunk
const sections = (list: Section[]) =>
  vi.spyOn(api, 'paperSections').mockResolvedValue({ sections: list, lenses: [] } as never)

function run(enabled = true, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
  return renderHook(() => useConclusion('p1', enabled), { wrapper })
}

describe('useConclusion', () => {
  it('reads the conclusion through its own chunks on the page, cut at 900 characters', async () => {
    sections([sec('conclusion', ['c1', 'c2'])])
    vi.spyOn(api, 'listChunks').mockResolvedValue([chunk('x', 'other'), chunk('c1', 'a'.repeat(600), 1), chunk('c2', 'b'.repeat(600), 2)])
    const { result } = run()
    expect(result.current.status).toBe('loading')
    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current.title).toBe('Conclusion')
    expect(result.current.page).toBe(9)
    expect(result.current.text).toHaveLength(901)
    expect(result.current.text.endsWith('…')).toBe(true)
    expect(result.current.text).not.toContain('other')
  })

  it('falls back to the discussion', async () => {
    sections([sec('intro', ['i']), sec('discussion', ['d'], 7)])
    vi.spyOn(api, 'listChunks').mockResolvedValue([chunk('d', 'We discuss.')])
    const { result } = run()
    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(result.current).toMatchObject({ title: 'Discussion', page: 7, text: 'We discuss.' })
  })

  it('has none when there is neither, and says whether sections exist at all', async () => {
    sections([sec('intro', ['i'])])
    const { result } = run()
    await waitFor(() => expect(result.current.status).toBe('none'))
    expect(result.current.noSections).toBe(false)
    sections([])
    const again = run()
    await waitFor(() => expect(again.result.current.noSections).toBe(true))
  })

  it('reports an error, and asks for nothing when disabled', async () => {
    vi.spyOn(api, 'paperSections').mockRejectedValue(new Error('boom'))
    const { result } = run()
    await waitFor(() => expect(result.current.status).toBe('error'))
    const spy = sections([])
    spy.mockClear()
    expect(run(false).result.current.status).toBe('none')
    expect(spy).not.toHaveBeenCalled()
  })

  it('prefetches sections under the hook\'s key', async () => {
    const spy = sections([sec('conclusion', ['c'])])
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } })
    await prefetchPaperSections(client, 'p1')
    expect(spy).toHaveBeenCalledTimes(1)
    vi.spyOn(api, 'listChunks').mockResolvedValue([chunk('c', 'Done.')])
    const { result } = run(true, client)
    await waitFor(() => expect(result.current.status).toBe('ready'))
    expect(spy).toHaveBeenCalledTimes(1)
  })
})
