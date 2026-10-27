// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render } from '@testing-library/react'
import { EditorView } from '@codemirror/view'
import { undo } from '@codemirror/commands'
import { useCallback, useRef, useState } from 'react'
import { expect, test } from 'vitest'
import { LatexEditor } from '../LatexEditor'
import type { PreambleEdit } from './insertBlock'
import { useInsertBlock, type InsertResult } from './useInsertBlock'

// jsdom has no layout; CodeMirror measures after the test awaits.
Range.prototype.getClientRects = () => ({ length: 0, item: () => null, [Symbol.iterator]: [][Symbol.iterator] }) as unknown as DOMRectList
Range.prototype.getBoundingClientRect = () => new DOMRect()

const MAIN = '\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}'

/** The real LatexEditor wired the way SourcePane/ManuscriptPage wire it: the value is React state, edits come back through onChange. */
function Harness({ out }: { out: { run?: (code: string, pk: string[]) => Promise<InsertResult> } }) {
  const [value, setValue] = useState(MAIN)
  const textNow = useRef(MAIN)
  const insertRef = useRef<((t: string, b?: boolean, pre?: PreambleEdit) => void) | null>(null)
  const change = (next: string) => { textNow.current = next; setValue(next) }
  const insert = useCallback((t: string, b: boolean, pre?: PreambleEdit) => {
    if (!insertRef.current) return false
    insertRef.current(t, b, pre)
    return true
  }, [])
  out.run = useInsertBlock({
    manuscriptId: 'm1', mainFile: 'main.tex', openPath: 'main.tex', getText: () => textNow.current, hasEditor: () => !!insertRef.current, insert,
  })
  return <LatexEditor value={value} onChange={change} errors={[]} onSave={() => {}} registerInsert={(f) => { insertRef.current = f }} />
}

test('the packages and the block both land in the open main file, as one undoable change', async () => {
  const out: { run?: (code: string, pk: string[]) => Promise<InsertResult> } = {}
  const { container } = render(<QueryClientProvider client={new QueryClient()}><Harness out={out} /></QueryClientProvider>)
  const view = EditorView.findFromDOM(container.querySelector('.cm-editor') as HTMLElement)!
  view.dispatch({ selection: { anchor: MAIN.indexOf('Hi') } })
  await act(async () => { expect(await out.run!('\\begin{table}\\end{table}', ['booktabs'])).toEqual({ ok: true }) })
  const doc = () => view.state.doc.toString()
  expect(doc()).toContain('\\usepackage{booktabs}\n\\begin{document}')
  expect(doc()).toContain('\\begin{table}\\end{table}')
  expect(doc()).toContain('Hi')
  // One transaction: a single undo removes the packages and the block together, so no half-state is left behind.
  undo(view)
  expect(doc()).toBe(MAIN)
})

test('packages already there: just the block, and the cursor ends after it', async () => {
  const out: { run?: (code: string, pk: string[]) => Promise<InsertResult> } = {}
  const { container } = render(<QueryClientProvider client={new QueryClient()}><Harness out={out} /></QueryClientProvider>)
  const view = EditorView.findFromDOM(container.querySelector('.cm-editor') as HTMLElement)!
  await act(async () => { await out.run!('B1', ['booktabs']) })
  await act(async () => { await out.run!('B2', ['booktabs']) })
  expect(view.state.doc.toString().match(/usepackage\{booktabs\}/g)).toHaveLength(1)
  expect(view.state.doc.toString()).toContain('B1')
  expect(view.state.doc.toString()).toContain('B2')
})
