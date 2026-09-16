import type { ChatModel } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { settingsHref } from '@/lib/route'

const MANAGE = 'manage'

type Props = {
  models: ChatModel[]
  /** The model the next question uses; null shows the placeholder. */
  value: string | null
  onChange: (modelId: string) => void
}

/** The chat composer's model dropdown: `name · connection`, a Cloud tag on non-local models, then "Manage models…". */
export function ModelPicker({ models, value, onChange }: Props) {
  function handleChange(next: string) {
    if (next === MANAGE) return void (location.hash = settingsHref)
    onChange(next)
  }
  const selected = models.find((model) => model.id === value)

  // `''`, never undefined: an undefined value makes Radix uncontrolled, so a removed model would stay shown.
  return (
    <Select value={value ?? ''} onValueChange={handleChange}>
      <SelectTrigger size="sm" aria-label="Model" className="max-w-56">
        {/* Explicit children, no badge: without this Radix portals the whole selected item (Cloud badge included)
            into the closed trigger, which breaks truncation for a cloud model. */}
        <SelectValue placeholder="Choose a model">{selected && `${selected.name} · ${selected.connection_label}`}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {models.map((model) => (
          <SelectItem key={model.id} value={model.id}>
            <span className="truncate">
              {model.name} · {model.connection_label}
            </span>
            {!model.is_local && (
              <Badge variant="outline" className="cloud-tag">
                Cloud
              </Badge>
            )}
          </SelectItem>
        ))}
        <SelectSeparator />
        <SelectItem value={MANAGE}>Manage models…</SelectItem>
      </SelectContent>
    </Select>
  )
}
