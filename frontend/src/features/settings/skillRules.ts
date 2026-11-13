import { ApiError, type LensId, type Skill, type SkillCreate, type SkillUpdate } from '@/api/client'

export type Scope = Skill['scope']
export type ChatKind = 'paper' | 'workspace'
export type SkillDraft = { label: string; description: string; scope: Scope; instructions: string; lens: LensId }

export const LABEL_MAX = 80
export const DESCRIPTION_MAX = 200
export const INSTRUCTIONS_MAX = 8000

export const SCOPE_LABELS: Record<Scope, string> = { paper: 'Paper', workspace: 'Workspace', both: 'Both' }
export const STATE_LABELS: Record<Skill['state'], string> = { builtin: 'Built-in', edited: 'Edited', custom: 'Custom' }

const ERROR_MESSAGES: Record<string, string> = {
  skill_label_taken: 'Another skill already has this label. Choose a different one.',
  skill_not_found: 'That skill no longer exists. Refresh the list.',
  skill_scope: "That skill can't be the default for this kind of chat.",
  builtin_skill: 'Built-in skills cannot be deleted. Hide one instead.',
  custom_skill: 'Only built-in skills can be reset.',
}

/** Whether a skill's scope lets it be the default for this chat kind. */
export const allowsDefault = (scope: Scope, kind: ChatKind): boolean => scope === kind || scope === 'both'

/** Joins skill lists, keeping the first list's order and each skill once. */
export function mergeSkillLists(...lists: (readonly Skill[] | undefined)[]): Skill[] {
  const byId = new Map<string, Skill>()
  for (const list of lists) for (const skill of list ?? []) if (!byId.has(skill.id)) byId.set(skill.id, skill)
  return [...byId.values()]
}

/** "<label> (copy)", or "(copy 2)", "(copy 3)"… while the name is taken. Case-insensitive, within the label limit. */
export function duplicateLabel(label: string, taken: readonly string[]): string {
  const names = new Set(taken.map((name) => name.toLowerCase()))
  for (let n = 1; ; n += 1) {
    const suffix = n === 1 ? ' (copy)' : ` (copy ${n})`
    const candidate = `${label.slice(0, LABEL_MAX - suffix.length)}${suffix}`
    if (!names.has(candidate.toLowerCase())) return candidate
  }
}

export const draftOf = (skill?: Skill): SkillDraft =>
  skill
    ? { label: skill.label, description: skill.description, scope: skill.scope, instructions: skill.instructions, lens: skill.lens }
    : { label: '', description: '', scope: 'both', instructions: '', lens: 'full' }

export const createBody = (draft: SkillDraft): SkillCreate => ({
  label: draft.label.trim(),
  description: draft.description.trim(),
  scope: draft.scope,
  instructions: draft.instructions,
  lens: draft.lens,
})

/** Only the fields the draft changed, so editing a built-in does not pin the fields it did not touch. */
export function changedFields(skill: Skill, draft: SkillDraft): SkillUpdate {
  const label = draft.label.trim()
  const description = draft.description.trim()
  return {
    ...(label !== skill.label && { label }),
    ...(description !== skill.description && { description }),
    ...(draft.scope !== skill.scope && { scope: draft.scope }),
    ...(draft.instructions !== skill.instructions && { instructions: draft.instructions }),
    ...(draft.lens !== skill.lens && { lens: draft.lens }),
  }
}

/** The first problem with a draft, in plain words, or null when it can be saved. */
export function validateDraft(draft: SkillDraft): string | null {
  if (draft.label.trim() === '') return 'Give the skill a label.'
  if (draft.label.trim().length > LABEL_MAX) return `Labels can be ${LABEL_MAX} characters or fewer.`
  if (draft.description.trim().length > DESCRIPTION_MAX) return `Descriptions can be ${DESCRIPTION_MAX} characters or fewer.`
  if (draft.instructions.trim() === '') return 'Write the instructions the model should follow.'
  if (draft.instructions.length > INSTRUCTIONS_MAX) return `Instructions can be ${INSTRUCTIONS_MAX} characters or fewer.`
  return null
}

export function skillErrorMessage(error: unknown): string {
  if (error instanceof ApiError && ERROR_MESSAGES[error.code]) return ERROR_MESSAGES[error.code]
  return error instanceof Error ? error.message : 'Something went wrong. Try again.'
}
