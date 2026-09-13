import { useEffect, useState } from 'react'
import type { Note } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { HighlightColorPicker } from './HighlightColorPicker'
import { ProvenanceBadge } from './ProvenanceBadge'

type Props = {
  note: Note
  paperId: string
  active?: boolean
  /** The hover card's version: no quote or page link (the highlight is right there), and not an `article.note`. */
  compact?: boolean
  startEditing?: boolean
  onSelect?: () => void
  onUpdate: (body: string) => Promise<boolean>
  onColorChange: (hex: string) => Promise<boolean>
  onDelete: () => Promise<void>
  /** Told whenever editing starts or stops, and "stopped" when the card unmounts. */
  onEditingChange?: (editing: boolean) => void
  className?: string
}

export function NoteCard({
  note,
  paperId,
  active = false,
  compact = false,
  startEditing = false,
  onSelect,
  onUpdate,
  onColorChange,
  onDelete,
  onEditingChange,
  className,
}: Props) {
  const [editing, setEditing] = useState(startEditing)
  const [body, setBody] = useState(note.body)
  const anchor = note.anchors.find((a) => a.paper_id === paperId)

  useEffect(() => {
    onEditingChange?.(editing)
    return () => onEditingChange?.(false)
  }, [editing, onEditingChange])

  async function save() {
    if (await onUpdate(body)) setEditing(false)
  }

  function cancel() {
    setBody(note.body)
    setEditing(false)
  }

  const Root = compact ? 'div' : 'article'
  return (
    <Root className={compact ? 'hover-note' : 'note'} data-note-id={note.id}>
      {/* Provenance is never subtle: every note shows a badge, and AI text gets its own background. */}
      <Card
        size="sm"
        className={cn(
          'bg-glass-strong ring-glass-border',
          note.provenance !== 'human' && 'bg-provenance-llm-surface',
          active && 'ring-2 ring-primary',
          className,
        )}
      >
        <CardHeader className="flex items-center justify-between">
          <ProvenanceBadge provenance={note.provenance} />
          {!compact && anchor && (
            <Button variant="link" size="xs" onClick={onSelect}>
              p. {anchor.page}
            </Button>
          )}
        </CardHeader>

        <CardContent className="flex flex-col gap-2">
          {!compact && anchor && (
            <blockquote className="cursor-pointer border-l-2 pl-2 text-muted-foreground" onClick={onSelect}>
              {anchor.quoted_text}
            </blockquote>
          )}
          {editing ? (
            <Textarea
              autoFocus
              aria-label="Edit note"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              onKeyDown={(e) => e.key === 'Escape' && cancel()}
            />
          ) : note.body ? (
            <p className={cn('whitespace-pre-wrap', compact && 'line-clamp-6')}>{note.body}</p>
          ) : (
            compact && anchor && <p className="line-clamp-3 text-muted-foreground">{anchor.quoted_text}</p>
          )}
          <HighlightColorPicker value={note.color} onChange={(hex) => void onColorChange(hex)} />
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
    </Root>
  )
}
