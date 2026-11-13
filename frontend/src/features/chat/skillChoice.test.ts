import { describe, expect, it } from 'vitest'
import type { Skill } from '@/api/client'
import { resolveSkill } from './skillChoice'

const skill = (id: string, flags: Partial<Skill> = {}) => ({ id, label: id, ...flags }) as Skill
const skills = [
  skill('builtin:limits', { is_paper_default: true }),
  skill('builtin:claims', { is_workspace_default: true }),
  skill('custom:mine'),
]

describe('resolveSkill', () => {
  it('starts on the kind default, so a paper chat and a workspace chat can have different ones', () => {
    expect(resolveSkill(skills, 'paper', undefined)).toBe('builtin:limits')
    expect(resolveSkill(skills, 'workspace', undefined)).toBe('builtin:claims')
  })

  it('starts on No skill when the kind has no default', () => {
    expect(resolveSkill([skill('custom:mine')], 'paper', undefined)).toBeNull()
  })

  it('keeps a pick that is still listed, including No skill', () => {
    expect(resolveSkill(skills, 'paper', 'custom:mine')).toBe('custom:mine')
    expect(resolveSkill(skills, 'paper', null)).toBeNull()
  })

  it('falls back to the default when the picked skill vanishes, else to No skill', () => {
    expect(resolveSkill(skills, 'paper', 'custom:gone')).toBe('builtin:limits')
    expect(resolveSkill([skill('custom:mine')], 'paper', 'custom:gone')).toBeNull()
  })
})
