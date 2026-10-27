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
  const calls = { insert: vi.fn((_t: string, _b: boolean, _p?: unknown) => true) }
  const deps = {
    manuscriptId: 'm1', mainFile: 'main.tex', openPath: 'main.tex', getText: () => MAIN,     hasEditor: () => true, insert: calls.insert, ...over,
  }
  return { ...calls, run: renderHook(() => useInsertBlock(deps), { wrapper }).result.current }
}

beforeEach(() => {
  vi.spyOn(api, 'getManuscriptFile').mockResolvedValue({ path: 'main.tex', text: MAIN, updated_at: 'T1' } as never)
  vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue({ path: 'main.tex', size: 1, updated_at: 'T2' } as never)
})
afterEach(() => vi.restoreAllMocks())

test('main open: the missing lines ride along with the block in one editor insert', async () => {
  const s = setup()
  expect(await s.run('BLOCK', ['booktabs'])).toEqual({ ok: true })
  expect(s.insert).toHaveBeenCalledTimes(1)
  expect(s.insert).toHaveBeenCalledWith('BLOCK', true, { line: 2, col: 0, text: '\\usepackage{booktabs}\n' })
  expect(api.saveManuscriptFile).not.toHaveBeenCalled()
})

test('main open with the packages already there: no preamble edit at all', async () => {
  const s = setup({ getText: () => MAIN.replace('\\begin', '\\usepackage{booktabs}\n\\begin') })
  expect(await s.run('BLOCK', ['booktabs'])).toEqual({ ok: true })
  expect(s.insert).toHaveBeenCalledWith('BLOCK', true, undefined)
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

test('main open but its live text is unavailable: refuses rather than saving under a live buffer', async () => {
  const s = setup({ getText: () => undefined })
  expect(await s.run('BLOCK', ['booktabs'])).toEqual({ ok: false, message: 'Open the main file in the editor and try again.' })
  expect(api.saveManuscriptFile).not.toHaveBeenCalled()
  expect(s.insert).not.toHaveBeenCalled()
})

test('the editor closing while main is fetched writes nothing', async () => {
  let open = true
  const s = setup({ openPath: 'b.tex', hasEditor: () => open })
  vi.mocked(api.getManuscriptFile).mockImplementation(async () => { open = false; return { path: 'main.tex', text: MAIN, updated_at: 'T1' } as never })
  expect((await s.run('BLOCK', ['booktabs'])).ok).toBe(false)
  expect(api.saveManuscriptFile).not.toHaveBeenCalled()
})

test('the editor closing between the save and the insert says the packages were added', async () => {
  let open = true
  const s = setup({ openPath: 'b.tex', hasEditor: () => open })
  vi.mocked(api.saveManuscriptFile).mockImplementation(async () => { open = false; return { path: 'main.tex', size: 1, updated_at: 'T2' } as never })
  s.insert.mockReturnValue(false)
  expect(await s.run('BLOCK', ['booktabs'])).toEqual({ ok: false, message: 'The packages were added; insert the block again.' })
})
