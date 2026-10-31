// @vitest-environment jsdom
import { render, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { undoDepth } from '@codemirror/commands'
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

test('Mod-Alt-K reports the cite key under the cursor, and only then', () => {
  const onCiteKey = vi.fn()
  const { container } = render(<LatexEditor value={'a \\citep{lewis20, b}\nplain'} onChange={() => {}} errors={[]} onSave={() => {}} onCiteKey={onCiteKey} />)
  const view = cm(container)
  view.dispatch({ selection: { anchor: 12 } })
  press(container, { key: 'k', code: 'KeyK', ctrlKey: true, altKey: true })
  press(container, { key: 'k', code: 'KeyK', metaKey: true, altKey: true })
  expect(onCiteKey).toHaveBeenCalledWith('lewis20')
  onCiteKey.mockClear()
  view.dispatch({ selection: { anchor: view.state.doc.line(2).from + 2 } })
  press(container, { key: 'k', code: 'KeyK', ctrlKey: true, altKey: true })
  press(container, { key: 'k', code: 'KeyK', metaKey: true, altKey: true })
  expect(onCiteKey).not.toHaveBeenCalled()
})

test('insert goes to the last cursor (the end if it never moved), is a normal edit, and takes focus', () => {
  const onChange = vi.fn()
  let insert: ((t: string) => void) | null = null
  const { container, unmount } = render(<LatexEditor value="ab" onChange={onChange} errors={[]} onSave={() => {}} registerInsert={(f) => { insert = f }} />)
  insert!('X')
  expect(cm(container).state.doc.toString()).toBe('abX')
  expect(onChange).toHaveBeenLastCalledWith('abX')
  expect(cm(container).hasFocus).toBe(true)
  cm(container).dispatch({ selection: { anchor: 1 } })
  cm(container).contentDOM.blur()
  insert!('Y')
  expect(onChange).toHaveBeenLastCalledWith('aYbX')
  unmount()
  expect(insert).toBeNull()
})

test('an insert never replaces a selection left in an unfocused editor', () => {
  let insert: ((t: string) => void) | null = null
  const { container } = render(<LatexEditor value="abc" onChange={() => {}} errors={[]} onSave={() => {}} registerInsert={(f) => { insert = f }} />)
  cm(container).dispatch({ selection: { anchor: 0, head: 2 } })
  insert!('X')
  expect(cm(container).state.doc.toString()).toBe('abXc')
})

test('an inserted comment (an AI note) lands on lines of its own, so it never comments out the researcher\'s text', () => {
  let insert: ((t: string) => void) | null = null
  const { container } = render(<LatexEditor value="We show that results hold." onChange={() => {}} errors={[]} onSave={() => {}} registerInsert={(f) => { insert = f }} />)
  const view = cm(container)
  view.dispatch({ selection: { anchor: 'We show that '.length } })
  insert!('% AI note (not your text): x')
  expect(view.state.doc.toString()).toBe('We show that \n% AI note (not your text): x\nresults hold.')
  expect(view.state.doc.lineAt(view.state.selection.main.head).text).toBe('results hold.') // outside the comment
  // At a line start no blank line goes before it.
  view.dispatch({ selection: { anchor: 0 } })
  insert!('% a')
  expect(view.state.doc.line(1).text).toBe('% a')
  expect(view.state.doc.line(2).text).toBe('We show that ')
})

test('after a comment inserted at a line end (or on an empty line), what you type next is on its own, uncommented line', () => {
  let insert: ((t: string) => void) | null = null
  const { container } = render(<LatexEditor value={'results hold.\n\nNext.'} onChange={() => {}} errors={[]} onSave={() => {}} registerInsert={(f) => { insert = f }} />)
  const view = cm(container)
  const type = (word: string) => view.dispatch(view.state.replaceSelection(word))
  view.dispatch({ selection: { anchor: 'results hold.'.length } })
  insert!('% b')
  type('Typed')
  view.dispatch({ selection: { anchor: view.state.doc.line(4).from } }) // the empty line
  insert!('% c')
  type('More')
  expect(view.state.doc.toString()).toBe('results hold.\n% b\nTyped\n% c\nMore\nNext.')
})

test('Mod-e asks to find evidence for the selection or cursor, and nothing else takes the key', () => {
  const onFindEvidence = vi.fn()
  const { container } = render(<LatexEditor value={'One. Two.'} onChange={() => {}} errors={[]} onSave={() => {}} onFindEvidence={onFindEvidence} />)
  const view = cm(container)
  view.dispatch({ selection: { anchor: 2, head: 5 } })
  const notPrevented = press(container, { key: 'e', code: 'KeyE', ctrlKey: true })
  expect(onFindEvidence).toHaveBeenCalledWith('One. Two.', 2, 5) // the editor's own text, with its own positions
  expect(notPrevented).toBe(false) // handled: the browser does not see it
})

test('an inserted block gets lines of its own: a break before unless at a line start, after unless at a line end', () => {
  let insert: ((t: string, block?: boolean) => void) | null = null
  const { container } = render(<LatexEditor value={'ab cd\n\nend'} onChange={() => {}} errors={[]} onSave={() => {}} registerInsert={(f) => { insert = f }} />)
  const view = cm(container)
  view.dispatch({ selection: { anchor: 3 } })
  insert!('\\begin{table}', true)
  expect(view.state.doc.toString()).toBe('ab \n\\begin{table}\ncd\n\nend')
  view.dispatch({ selection: { anchor: view.state.doc.toString().indexOf('\n\nend') + 1 } }) // the empty line
  insert!('T', true)
  expect(view.state.doc.toString()).toBe('ab \n\\begin{table}\ncd\nT\nend')
})

test('a new value from outside keeps the cursor on its line and column, clamped to the new text', () => {
  const { container, rerender } = render(<LatexEditor value={'one\ntwo words\nthree'} onChange={() => {}} errors={[]} onSave={() => {}} />)
  const view = cm(container)
  view.dispatch({ selection: { anchor: view.state.doc.line(2).from + 5 } })
  rerender(<LatexEditor value={'one\ntwo wo more\nthree\nfour'} onChange={() => {}} errors={[]} onSave={() => {}} />)
  expect(view.state.selection.main.head).toBe(view.state.doc.line(2).from + 5)
  rerender(<LatexEditor value={'a\nbc'} onChange={() => {}} errors={[]} onSave={() => {}} />)
  expect(view.state.selection.main.head).toBe(view.state.doc.line(2).to) // clamped to the shorter line
  rerender(<LatexEditor value={'x'} onChange={() => {}} errors={[]} onSave={() => {}} />)
  expect(view.state.selection.main.head).toBe(1) // line gone: the end
})

test('a new value from outside is not undoable', () => {
  const { container, rerender } = render(<LatexEditor value="one" onChange={() => {}} errors={[]} onSave={() => {}} />)
  rerender(<LatexEditor value="two" onChange={() => {}} errors={[]} onSave={() => {}} />)
  expect(undoDepth(cm(container).state)).toBe(0)
})
