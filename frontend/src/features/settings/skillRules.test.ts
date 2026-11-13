import { describe, expect, it } from 'vitest'
import { ApiError, type Skill } from '@/api/client'
import {
  allowsDefault,
  changedFields,
  createBody,
  draftOf,
  duplicateLabel,
  mergeSkillLists,
  skillErrorMessage,
  validateDraft,
} from './skillRules'

const skill = (overrides: Partial<Skill> = {}): Skill => ({
  id: 'builtin:check-evaluation',
  label: 'Check the evaluation',
  description: 'Looks at how the paper tested its claims.',
  scope: 'paper',
  instructions: 'Read the method first.',
  version: 1,
  is_listed: true,
  is_paper_default: false,
  is_workspace_default: false,
  state: 'builtin',
  ...overrides,
})

describe('duplicateLabel', () => {
  it('adds " (copy)", then numbers it while taken, ignoring case', () => {
    expect(duplicateLabel('Check the evaluation', ['Check the evaluation'])).toBe('Check the evaluation (copy)')
    expect(duplicateLabel('Check the evaluation', ['Check the evaluation', 'check the evaluation (COPY)'])).toBe(
      'Check the evaluation (copy 2)',
    )
    expect(
      duplicateLabel('Check the evaluation', ['Check the evaluation', 'Check the evaluation (copy)', 'Check the evaluation (copy 2)']),
    ).toBe('Check the evaluation (copy 3)')
  })

  it('keeps the copy within the 80-character label limit', () => {
    const long = 'x'.repeat(80)
    const copy = duplicateLabel(long, [long])
    expect(copy.length).toBeLessThanOrEqual(80)
    expect(copy.endsWith(' (copy)')).toBe(true)
  })
})

describe('allowsDefault', () => {
  it.each([
    ['paper', 'paper', true],
    ['paper', 'workspace', false],
    ['workspace', 'workspace', true],
    ['workspace', 'paper', false],
    ['both', 'paper', true],
    ['both', 'workspace', true],
  ] as const)('scope %s allows a default for %s chats: %s', (scope, kind, expected) => {
    expect(allowsDefault(scope, kind)).toBe(expected)
  })
})

describe('mergeSkillLists', () => {
  it('keeps the first list order and lists each skill once', () => {
    const a = skill({ id: 'builtin:a', label: 'A' })
    const b = skill({ id: 'builtin:b', label: 'B' })
    const c = skill({ id: 'custom:c', label: 'C', state: 'custom' })
    expect(mergeSkillLists([a, b], [b, c], undefined).map((s) => s.id)).toEqual(['builtin:a', 'builtin:b', 'custom:c'])
  })
})

describe('changedFields', () => {
  it('sends nothing for an unchanged draft', () => {
    const s = skill()
    expect(changedFields(s, draftOf(s))).toEqual({})
  })

  it('sends only the fields that changed, trimmed', () => {
    const s = skill()
    expect(changedFields(s, { ...draftOf(s), label: '  Checks  ', scope: 'both' })).toEqual({ label: 'Checks', scope: 'both' })
  })
})

describe('createBody and draftOf', () => {
  it('trims the label and description, and starts a new skill on both chats', () => {
    expect(createBody({ label: ' Mine ', description: ' Short ', scope: 'paper', instructions: 'Do it.' })).toEqual({
      label: 'Mine',
      description: 'Short',
      scope: 'paper',
      instructions: 'Do it.',
    })
    expect(draftOf(undefined)).toEqual({ label: '', description: '', scope: 'both', instructions: '' })
  })
})

describe('validateDraft', () => {
  const ok = { label: 'Mine', description: '', scope: 'both' as const, instructions: 'Do it.' }

  it('accepts a complete draft', () => {
    expect(validateDraft(ok)).toBeNull()
  })

  it('asks for a label and instructions', () => {
    expect(validateDraft({ ...ok, label: '   ' })).toBe('Give the skill a label.')
    expect(validateDraft({ ...ok, instructions: '  ' })).toBe('Write the instructions the model should follow.')
  })

  it('refuses a label over 80 characters, a description over 200 and instructions over 8000', () => {
    expect(validateDraft({ ...ok, label: 'x'.repeat(81) })).toMatch(/80 characters/)
    expect(validateDraft({ ...ok, description: 'x'.repeat(201) })).toMatch(/200 characters/)
    expect(validateDraft({ ...ok, instructions: 'x'.repeat(8001) })).toMatch(/8000 characters/)
  })
})

describe('skillErrorMessage', () => {
  it('explains a taken label in plain words', () => {
    const error = new ApiError('Conflict', 409, { detail: 'skill_label_taken' })
    expect(skillErrorMessage(error)).toBe('Another skill already has this label. Choose a different one.')
  })

  it('passes an ordinary error message through, and falls back for anything else', () => {
    expect(skillErrorMessage(new Error('Network down'))).toBe('Network down')
    expect(skillErrorMessage('nope')).toBe('Something went wrong. Try again.')
  })
})
