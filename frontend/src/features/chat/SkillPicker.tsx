import type { Skill } from '@/api/client'
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { settingsHref } from '@/lib/route'

const NO_SKILL = 'none'
const MANAGE = 'manage'

type Props = {
  /** The skills this chat's kind can use, listed. */
  skills: Skill[]
  /** The skill the next question uses; null is No skill. */
  value: string | null
  onChange: (skillId: string | null) => void
}

/** The chat composer's skill dropdown: "No skill", the skills for this kind, then "Manage skills…". */
export function SkillPicker({ skills, value, onChange }: Props) {
  function handleChange(next: string) {
    if (next === MANAGE) return void (location.hash = `${settingsHref}/skills`)
    onChange(next === NO_SKILL ? null : next)
  }
  const selected = skills.find((skill) => skill.id === value)

  return (
    <Select value={value ?? NO_SKILL} onValueChange={handleChange}>
      <SelectTrigger size="sm" aria-label="Skill" className="max-w-56">
        {/* Explicit children, as in ModelPicker: keeps a long label truncating inside the closed trigger. */}
        <SelectValue placeholder="No skill">{selected ? selected.label : 'No skill'}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NO_SKILL}>No skill</SelectItem>
        {skills.map((skill) => (
          <SelectItem key={skill.id} value={skill.id}>
            <span className="truncate">{skill.label}</span>
          </SelectItem>
        ))}
        <SelectSeparator />
        <SelectItem value={MANAGE}>Manage skills…</SelectItem>
      </SelectContent>
    </Select>
  )
}
