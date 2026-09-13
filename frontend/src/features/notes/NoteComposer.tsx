import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import type { SelectionAnchor } from '../reader/selection'

type Props = {
  draft: SelectionAnchor
  onSave: (body: string) => Promise<boolean>
  onCancel: () => void
}

export function NoteComposer({ draft, onSave, onCancel }: Props) {
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
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <Card size="sm" className="ring-2 ring-primary">
        <CardContent className="flex flex-col gap-2">
          <blockquote className="border-l-2 pl-2 text-muted-foreground">{draft.quotedText}</blockquote>
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
