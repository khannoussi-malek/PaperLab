import type { Skill } from '@/api/client'

export type SkillKind = 'paper' | 'workspace'

/**
 * The skill the next question uses. `chosen` is what the reader picked this session: undefined until they pick
 * (the kind's default), null for No skill, else a skill id. A pick that is no longer listed falls back to the default.
 */
export function resolveSkill(skills: Skill[], kind: SkillKind, chosen: string | null | undefined): string | null {
  const defaultId = skills.find((skill) => (kind === 'paper' ? skill.is_paper_default : skill.is_workspace_default))?.id ?? null
  if (chosen === undefined) return defaultId
  if (chosen === null) return null
  return skills.some((skill) => skill.id === chosen) ? chosen : defaultId
}
