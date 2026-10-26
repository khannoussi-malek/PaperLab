// @vitest-environment jsdom
import { render } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { LatexEditor } from './LatexEditor'

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
