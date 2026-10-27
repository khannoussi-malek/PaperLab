// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError } from '@/api/client'
import { useInsertBlock } from './useInsertBlock'

const MAIN = '\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}'
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>

function setup(over: Partial<Parameters<typeof useInsertBlock>[0]> = {}) {
  const calls = { replace: vi.fn(), insert: vi.fn(() => true) }
  const deps = {
    manuscriptId: 'm1', mainFile: 'main.tex', openPath: 'main.tex', getText: () => MAIN, replace: calls.replace, canReplace: () => true,
    hasEditor: () => true, insert: calls.insert, ...over,
  }
  return { ...calls, run: renderHook(() => useInsertBlock(deps), { wrapper }).result.current }
}

beforeEach(() => {
  vi.spyOn(api, 'getManuscriptFile').mockResolvedValue({ path: 'main.tex', text: MAIN, updated_at: 'T1' } as never)
  vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue({ path: 'main.tex', size: 1, updated_at: 'T2' } as never)
})
afterEach(() => vi.restoreAllMocks())

test('main open: the missing lines go through the editor buffer, then the block is inserted as a block', async () => {
  const s = setup()
  expect(await s.run('BLOCK', ['booktabs'])).toEqual({ ok: true })
  expect(s.replace).toHaveBeenCalledWith(2, 0, '\\usepackage{booktabs}\n')
  expect(api.saveManuscriptFile).not.toHaveBeenCalled()
  expect(s.insert).toHaveBeenCalledWith('BLOCK', true)
})

test('main open with the packages already there: no preamble edit at all', async () => {
  const s = setup({ getText: () => MAIN.replace('\\begin', '\\usepackage{booktabs}\n\\begin') })
  expect(await s.run('BLOCK', ['booktabs'])).toEqual({ ok: true })
  expect(s.replace).not.toHaveBeenCalled()
  expect(s.insert).toHaveBeenCalledTimes(1)
})

test('another file open: a save based on the main file updated_at', async () => {
  const s = setup({ openPath: 'b.tex' })
  expect(await s.run('BLOCK', ['pgfplots'])).toEqual({ ok: true })
  expect(api.saveManuscriptFile).toHaveBeenCalledWith('m1', 'main.tex', '\\documentclass{article}\n\\usepackage{pgfplots}\n\\pgfplotsset{compat=1.18}\n\\begin{document}\nHi\n\\end{document}', 'T1')
  expect(s.insert).toHaveBeenCalledWith('BLOCK', true)
})

test('a conflict refuses with the copy and inserts nothing', async () => {
  vi.mocked(api.saveManuscriptFile).mockRejectedValue(new ApiError('file_changed', 409, { detail: 'file_changed', updated_at: 'T3' }))
  const s = setup({ openPath: 'b.tex' })
  expect(await s.run('BLOCK', ['booktabs'])).toEqual({ ok: false, message: 'The main file changed. Open it and try again.' })
  expect(s.insert).not.toHaveBeenCalled()
})

test('no editor open: nothing is written', async () => {
  const s = setup({ openPath: 'b.tex', hasEditor: () => false })
  expect((await s.run('BLOCK', ['booktabs'])).ok).toBe(false)
  expect(api.saveManuscriptFile).not.toHaveBeenCalled()
})
