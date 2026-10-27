// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { useLensReader } from './useLensReader'

let chunks: { data?: unknown[]; isError: boolean }
vi.mock('./queries', () => ({
  usePaperSections: () => ({ data: { sections: [], lenses: [] } }),
  usePaperChunks: () => chunks,
}))

it('a section clicked while the chunks still load jumps there once they arrive', () => {
  chunks = { data: undefined, isError: false }
  const onJump = vi.fn()
  const { result, rerender } = renderHook(() => useLensReader('p1', 'lens', onJump))
  act(() => result.current.jumpToChunk('c2'))
  expect(onJump).not.toHaveBeenCalled()

  chunks = { data: [{ id: 'c1', page: 1, bbox: [[0, 0, 1, 1]] }, { id: 'c2', page: 2, bbox: [[0, 0, 2, 2]] }], isError: false }
  rerender()
  expect(onJump).toHaveBeenCalledExactlyOnceWith(2, [[0, 0, 2, 2]])
  rerender()
  expect(onJump).toHaveBeenCalledOnce()
})

it('drops the waiting jump when the chunks fail to load', () => {
  chunks = { data: undefined, isError: false }
  const onJump = vi.fn()
  const { result, rerender } = renderHook(() => useLensReader('p1', 'lens', onJump))
  act(() => result.current.jumpToChunk('c2'))
  chunks = { data: undefined, isError: true }
  rerender()
  chunks = { data: [{ id: 'c2', page: 2, bbox: [] }], isError: false }
  rerender()
  expect(onJump).not.toHaveBeenCalled()
})
