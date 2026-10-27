// @vitest-environment jsdom
import { render, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { LatexEditor, latexTheme } from './LatexEditor'

test('shows the text and follows a new value', () => {
  const onChange = vi.fn()
  const { container, rerender } = render(<LatexEditor value="\section{A}" onChange={onChange} errors={[{ line: 1, message: 'bad' }]} onSave={() => {}} />)
  expect(container.querySelector('.cm-content')).toHaveTextContent('\\section{A}')
  rerender(<LatexEditor value="new text" onChange={onChange} errors={[]} onSave={() => {}} />)
  expect(container.querySelector('.cm-content')).toHaveTextContent('new text')
})

test('a new value from outside is not reported back as an edit', () => {
  const onChange = vi.fn()
  const { rerender } = render(<LatexEditor value="one" onChange={onChange} errors={[]} onSave={() => {}} />)
  rerender(<LatexEditor value="two" onChange={onChange} errors={[]} onSave={() => {}} />)
  expect(onChange).not.toHaveBeenCalled()
})

test('the theme says whether it is dark', () => {
  expect(EditorState.create({ extensions: [latexTheme(true)] }).facet(EditorView.darkTheme)).toBe(true)
  expect(EditorState.create({ extensions: [latexTheme(false)] }).facet(EditorView.darkTheme)).toBe(false)
})

test('follows the app switching to dark', async () => {
  const { container } = render(<LatexEditor value="x" onChange={() => {}} errors={[]} onSave={() => {}} />)
  const isDark = () => EditorView.findFromDOM(container.querySelector<HTMLElement>('.cm-editor')!)!.state.facet(EditorView.darkTheme)
  expect(isDark()).toBe(false)
  document.documentElement.classList.add('dark')
  await waitFor(() => expect(isDark()).toBe(true))
  document.documentElement.classList.remove('dark')
})

const cm = (container: HTMLElement) => EditorView.findFromDOM(container.querySelector<HTMLElement>('.cm-editor')!)!
const press = (container: HTMLElement, init: KeyboardEventInit) =>
  container.querySelector('.cm-content')!.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init }))

test('reports the cursor line (1-based) when the selection moves, not on every keystroke elsewhere', () => {
  const onCursor = vi.fn()
  const { container } = render(<LatexEditor value={'a\nb\nc'} onChange={() => {}} errors={[]} onSave={() => {}} onCursor={onCursor} />)
  const view = cm(container)
  view.dispatch({ selection: { anchor: view.state.doc.line(3).from } })
  expect(onCursor).toHaveBeenLastCalledWith(3)
  onCursor.mockClear()
  view.dispatch({ selection: { anchor: view.state.doc.line(3).from + 1 } }) // same line
  expect(onCursor).not.toHaveBeenCalled()
})

test('Mod-Alt-Up/Down step sections and Mod-Alt-P shows the line in the PDF', () => {
  const onSectionStep = vi.fn()
  const onShowInPdf = vi.fn()
  const { container } = render(<LatexEditor value={'a\nb'} onChange={() => {}} errors={[]} onSave={() => {}} onSectionStep={onSectionStep} onShowInPdf={onShowInPdf} />)
  const view = cm(container)
  view.dispatch({ selection: { anchor: view.state.doc.line(2).from } })
  press(container, { key: 'ArrowUp', ctrlKey: true, altKey: true })
  press(container, { key: 'ArrowDown', ctrlKey: true, altKey: true })
  press(container, { key: 'p', code: 'KeyP', ctrlKey: true, altKey: true })
  expect(onSectionStep.mock.calls).toEqual([[-1], [1]])
  expect(onShowInPdf).toHaveBeenCalledWith(2)
})

test('Alt-ArrowUp still moves the line (CodeMirror\'s own binding)', () => {
  const onSectionStep = vi.fn()
  const { container } = render(<LatexEditor value={'a\nb'} onChange={() => {}} errors={[]} onSave={() => {}} onSectionStep={onSectionStep} />)
  const view = cm(container)
  view.dispatch({ selection: { anchor: view.state.doc.line(2).from } })
  press(container, { key: 'ArrowUp', altKey: true })
  expect(view.state.doc.toString()).toBe('b\na')
  expect(onSectionStep).not.toHaveBeenCalled()
})
