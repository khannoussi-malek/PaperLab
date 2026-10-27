import { describe, expect, it } from 'vitest'
import { sectionStatus } from './sectionStatus'

const words = (n: number) => Array.from({ length: n }, (_, i) => `w${i}`).join(' ')

describe('sectionStatus', () => {
  it('is empty under 20 words', () => {
    expect(sectionStatus(words(19), 0)).toEqual({ status: 'empty', label: 'Empty', todos: 0 })
  })
  it('is ok from 20 words', () => {
    expect(sectionStatus(words(20), 0)).toEqual({ status: 'ok', label: 'Fine', todos: 0 })
  })
  it('counts todos in either form, any case', () => {
    expect(sectionStatus(`${words(30)}\n% todo: x`, 0)).toEqual({ status: 'todo', label: '1 TODO', todos: 1 })
    expect(sectionStatus(`${words(30)}\n% TODO a\n\\todo{b}`, 0)).toMatchObject({ label: '2 TODOs', todos: 2 })
  })
  it('puts errors before todos before empty', () => {
    expect(sectionStatus('% TODO', 1)).toMatchObject({ status: 'error', label: '1 compile error', todos: 1 })
    expect(sectionStatus(words(30), 3)).toMatchObject({ status: 'error', label: '3 compile errors' })
    expect(sectionStatus('% TODO x', 0)).toMatchObject({ status: 'todo' })
  })
})
