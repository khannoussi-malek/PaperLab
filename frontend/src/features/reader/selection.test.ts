// @vitest-environment jsdom
import { afterEach, expect, test } from 'vitest'
import { readAbstractSelection } from './selection'

function select(element: Element) {
  const range = document.createRange()
  range.selectNodeContents(element)
  window.getSelection()!.removeAllRanges()
  window.getSelection()!.addRange(range)
}

afterEach(() => {
  window.getSelection()!.removeAllRanges()
  document.body.innerHTML = ''
})

test('text selected in the abstract is its quote; text elsewhere (the title) is not', () => {
  document.body.innerHTML = '<h2>Sleep and memory</h2><p class="paper-abstract">Sleep helps memory.</p>'
  select(document.querySelector('.paper-abstract')!)
  expect(readAbstractSelection()).toEqual({ page: 0, rects: [], quotedText: 'Sleep helps memory.' })
  select(document.querySelector('h2')!)
  expect(readAbstractSelection()).toBeNull()
})

test('a selection that runs from the title into the abstract is no quote', () => {
  document.body.innerHTML = '<h2>Sleep and memory</h2><p class="paper-abstract">Sleep helps memory.</p>'
  const range = document.createRange()
  range.setStart(document.querySelector('h2')!.firstChild!, 0)
  range.setEnd(document.querySelector('.paper-abstract')!.firstChild!, 5)
  window.getSelection()!.removeAllRanges()
  window.getSelection()!.addRange(range)
  expect(readAbstractSelection()).toBeNull()
})
