// @vitest-environment jsdom
import { renderHook } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { usePdfDocument } from './usePdfDocument'

const getDocument = vi.hoisted(() => vi.fn(() => ({ promise: new Promise(() => {}), destroy: vi.fn() })))
vi.mock('./pdfjs', () => ({ getDocument, pdfWorker: null }))

test('with no url it stays idle: no request, no document, no error', () => {
  const { result } = renderHook(() => usePdfDocument(null))
  expect(getDocument).not.toHaveBeenCalled()
  expect(result.current).toEqual({ doc: null, error: null })
})

test('with a url it opens the document', () => {
  renderHook(() => usePdfDocument('/api/papers/p1/file'))
  expect(getDocument).toHaveBeenCalledWith({ url: '/api/papers/p1/file', worker: null })
})
