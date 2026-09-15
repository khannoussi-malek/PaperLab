import { describe, expect, it } from 'vitest'
import { aiMark } from './aiMark'

describe('aiMark', () => {
  it('names the model, its connection and the prompt version', () => {
    expect(aiMark('m', 'Conn', 1)).toBe('AI · m · Conn · prompt v1')
    expect(aiMark('fake:qwen3:8b', 'E2E connection 1a2b', 2)).toBe('AI · fake:qwen3:8b · E2E connection 1a2b · prompt v2')
  })

  it('leaves the connection out for answers saved before connections existed', () => {
    expect(aiMark('m', null, 1)).toBe('AI · m · prompt v1')
  })
})
