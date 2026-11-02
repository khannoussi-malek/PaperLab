import type { NoteKind } from '@/api/client'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { KIND_LABEL } from './noteKinds'

const NONE = 'none' // Radix items can't have an empty value

type Props = { value: NoteKind | null; onChange: (kind: NoteKind | null) => void; id?: string }

export function KindSelect({ value, onChange, id }: Props) {
  return (
    <Select value={value ?? NONE} onValueChange={(next) => onChange(next === NONE ? null : (next as NoteKind))}>
      <SelectTrigger id={id} size="sm" aria-label="Kind">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>Note</SelectItem>
        {Object.entries(KIND_LABEL).map(([kind, label]) => (
          <SelectItem key={kind} value={kind}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
