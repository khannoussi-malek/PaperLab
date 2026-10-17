import { describe, expect, it } from 'vitest'
import { EXCLUDE_REASONS, reasonLabel } from './hitReview'

describe('reasonLabel', () => {
  it('gives words for every stage-1 code and unspecified', () => {
    const expected: Record<string, string> = {
      wrong_topic: 'Wrong topic', wrong_study_type: 'Wrong study type', duplicate: 'Duplicate',
      language: 'Language', inaccessible: "Can't access", other: 'Other', unspecified: 'No reason given',
    }
    for (const code of [...EXCLUDE_REASONS, 'unspecified']) {
      expect(reasonLabel(code)).toBe(expected[code])
      expect(reasonLabel(code)).not.toContain('_')
    }
  })
  it('returns free text as written and a default for none', () => {
    expect(reasonLabel('not about LLMs')).toBe('not about LLMs')
    expect(reasonLabel(null)).toBe('No reason given')
    expect(reasonLabel(undefined)).toBe('No reason given')
  })
})
