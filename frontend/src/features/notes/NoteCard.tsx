import { useState } from 'react'
import type { Note } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { ProvenanceBadge } from './ProvenanceBadge'

type Props = {
  note: Note
  paperId: string
  active: boolean
  onSelect: () => void
  onUpdate: (body: string) => Promise<boolean>
  onDelete: () => Promise<void>
}

export function NoteCard({ note, paperId, active, onSelect, onUpdate, onDelete }: Props) {
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(note.body)
  const anchor = note.anchors.find((a) => a.paper_id === paperId)

  async function save() {
    if (await onUpdate(body)) setEditing(false)
  }

  function cancel() {
    setBody(note.body)
    setEditing(false)
  }

  return (
    <article className="note" data-note-id={note.id}>
      {/* Provenance is never subtle: every note shows a badge, and AI text gets its own background. */}
      <Card
        size="sm"
        className={cn(
          'bg-glass-strong ring-glass-border',
          note.provenance !== 'human' && 'bg-provenance-llm-surface',
          active && 'ring-2 ring-primary',
        )}
      >
        <CardHeader className="flex items-center justify-between">
          <ProvenanceBadge provenance={note.provenance} />
          {anchor && (
            <Button variant="link" size="xs" onClick={onSelect}>
              p. {anchor.page}
            </Button>
          )}
        </CardHeader>

        <CardContent className="flex flex-col gap-2">
          {anchor && (
            <blockquote className="cursor-pointer border-l-2 pl-2 text-muted-foreground" onClick={onSelect}>
              {anchor.quoted_text}
            </blockquote>
          )}
          {editing ? (
            <Textarea autoFocus aria-label="Edit note" value={body} onChange={(e) => setBody(e.target.value)} />
          ) : (
            note.body && <p className="whitespace-pre-wrap">{note.body}</p>
          )}
        </CardContent>

        <CardFooter className="justify-end gap-2">
          {editing ? (
            <>
              <Button variant="ghost" size="sm" onClick={cancel}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => void save()}>
                Save
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button variant="ghost" size="sm" className="text-destructive" onClick={() => void onDelete()}>
                Delete
              </Button>
            </>
          )}
        </CardFooter>
      </Card>
    </article>
  )
}
