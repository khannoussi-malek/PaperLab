import { useState } from 'react'
import { popIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { SelectionAnchor } from '../reader/selection'
import { HighlightColorPicker } from './HighlightColorPicker'

type Props = {
  draft: SelectionAnchor
  color: string
  onColorChange: (hex: string) => void
  onSave: (body: string) => Promise<boolean>
  onCancel: () => void
}

export function NoteComposer({ draft, color, onColorChange, onSave, onCancel }: Props) {
  const [body, setBody] = useState('')
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    await onSave(body)
    setSaving(false)
  }

  return (
    // A form, not an <article>: saved notes are the only articles in the panel.
    <form
      className={cn('origin-top', popIn)}
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <Card size="sm" className="bg-glass-strong ring-2 ring-primary">
        <CardContent className="flex flex-col gap-2">
          <blockquote className="line-clamp-2 border-l-2 pl-2 text-muted-foreground" title={draft.quotedText}>
            {draft.quotedText}
          </blockquote>
          <Textarea
            autoFocus
            aria-label="Note"
            placeholder="Your note (optional). Ctrl/⌘+Enter saves."
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                void save()
              }
              if (e.key === 'Escape') onCancel()
            }}
          />
          <HighlightColorPicker value={color} onChange={onColorChange} />
        </CardContent>
        <CardFooter className="justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            Save note
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}
