// @vitest-environment jsdom
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const tasks: { url: string; destroy: ReturnType<typeof vi.fn>; doc: object }[] = []
const getDocument = vi.fn(({ url }: { url: string }) => {
  const doc = { numPages: 1, url }
  const task = { url, doc, destroy: vi.fn(async () => {}), promise: Promise.resolve(doc) }
  tasks.push(task)
  return task
})
vi.mock('../reader/pdfjs', () => ({ getDocument: (o: { url: string }) => getDocument(o), pdfWorker: {} }))

import { acquirePdf, prefetchPdf, releasePdf, retainOnly, useCachedPdf } from './pdfCache'

beforeEach(() => { tasks.length = 0; getDocument.mockClear() })
afterEach(() => retainOnly([]))

it('shares one getDocument per url', () => {
  acquirePdf('/a'); acquirePdf('/a'); prefetchPdf('/a')
  expect(getDocument).toHaveBeenCalledTimes(1)
  releasePdf('/a'); releasePdf('/a')
})

it('retainOnly destroys the unreferenced rest and keeps the listed', () => {
  prefetchPdf('/a'); prefetchPdf('/b'); prefetchPdf('/c')
  retainOnly(['/b'])
  expect(tasks.find((t) => t.url === '/a')!.destroy).toHaveBeenCalled()
  expect(tasks.find((t) => t.url === '/c')!.destroy).toHaveBeenCalled()
  expect(tasks.find((t) => t.url === '/b')!.destroy).not.toHaveBeenCalled()
})

it('a mounted document is never destroyed under it, only after its last release', () => {
  acquirePdf('/a'); acquirePdf('/a')
  retainOnly([])
  const t = tasks[0]
  expect(t.destroy).not.toHaveBeenCalled()
  releasePdf('/a')
  expect(t.destroy).not.toHaveBeenCalled()
  releasePdf('/a')
  expect(t.destroy).toHaveBeenCalledTimes(1)
})

it('a retained document survives its release; a destroyed one is fetched afresh', () => {
  retainOnly(['/a'])
  acquirePdf('/a'); releasePdf('/a')
  expect(tasks[0].destroy).not.toHaveBeenCalled()
  retainOnly([])
  expect(tasks[0].destroy).toHaveBeenCalledTimes(1)
  acquirePdf('/a')
  expect(getDocument).toHaveBeenCalledTimes(2)
  releasePdf('/a')
})

it('useCachedPdf hands over the doc and releases on unmount', async () => {
  const { result, unmount } = renderHook(() => useCachedPdf('/a'))
  expect(result.current.doc).toBeNull()
  await waitFor(() => expect(result.current.doc).toBe(tasks[0].doc))
  unmount()
  expect(tasks[0].destroy).toHaveBeenCalledTimes(1)
})

it('useCachedPdf(null) asks for nothing', () => {
  renderHook(() => useCachedPdf(null))
  expect(getDocument).not.toHaveBeenCalled()
})
