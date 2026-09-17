import { describe, expect, it } from 'vitest'
import { emailProblem, keyLine } from './paperSources'

const PROBLEM = 'Enter an email address like name@example.org.'

describe('emailProblem', () => {
  it('accepts an address, ignoring the spaces around it', () => {
    expect(emailProblem('name@example.org')).toBeNull()
    expect(emailProblem('  first.last+tag@lab.uni.edu \n')).toBeNull()
  })

  it("refuses what the server refuses, in the server's words", () => {
    for (const text of ['name', 'name@example', 'name@@example.org', 'first last@example.org', '@example.org']) {
      expect(emailProblem(text), text).toBe(PROBLEM)
    }
  })

  it('allows 254 characters and no more', () => {
    const domain = '@example.org' // 12 characters
    expect(emailProblem(`${'a'.repeat(242)}${domain}`)).toBeNull()
    expect(emailProblem(`${'a'.repeat(243)}${domain}`)).toBe(PROBLEM)
  })

  it('has nothing to say about blank text, which saves nothing', () => {
    expect(emailProblem('')).toBeNull()
    expect(emailProblem('   ')).toBeNull()
  })
})

describe('keyLine', () => {
  it("names the key's last characters, or just says a key is saved when it's too short to hint", () => {
    expect(keyLine('T123')).toBe('Key ending in T123')
    expect(keyLine(null)).toBe('Key saved')
  })
})
