import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type Props = {
  reasons: readonly { key: string; label: string }[]
  onPick: (reason: string, note?: string) => void
  onCancel: () => void
  /** The reason that asks for a one-line note first. */
  noteFor: string
}

/** Why a paper is not relevant: numbered chips; `noteFor` opens a one-line note (Enter commits, Esc cancels). */
export function ReasonChips({ reasons, onPick, onCancel, noteFor }: Props) {
  const [noting, setNoting] = useState(false)
  const [note, setNote] = useState('')
  return (
    <div role="group" aria-label="Reason" className="flex flex-wrap items-center gap-2">
      {reasons.map((r, i) => (
        <Button
          key={r.key}
          type="button"
          variant="outline"
          size="sm"
          data-reason-chip={r.key}
          onClick={() => (r.key === noteFor ? setNoting(true) : onPick(r.key, undefined))}
        >
          {i + 1} {r.label}{r.key === noteFor ? '…' : ''}
        </Button>
      ))}
      {noting && (
        <Input
          autoFocus
          aria-label="Note"
          placeholder="A few words (optional), then Enter"
          value={note}
          maxLength={500}
          className="w-64"
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onPick(noteFor, note.trim() || undefined)
            else if (e.key === 'Escape') onCancel()
          }}
        />
      )}
    </div>
  )
}
