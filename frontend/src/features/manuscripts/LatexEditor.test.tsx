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
