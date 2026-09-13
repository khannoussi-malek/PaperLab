import type { CSSProperties } from 'react'
import type { Note } from '@/api/client'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { ProvenanceBadge } from './ProvenanceBadge'

type Props = {
  notes: Note[]
  paperId: string
  /** Position inside the page overlay, in CSS pixels of the page. */
  style: CSSProperties
}

/** Read-only preview of the notes under the pointer. The overlay ignores the mouse, so selection still works. */
export function NoteHoverCard({ notes, paperId, style }: Props) {
  return (
    // Blur earns its place here: the card floats over the PDF text it would otherwise clash with.
    <Card
      size="sm"
      className="note-hover-card absolute z-10 w-72 gap-2 bg-glass-strong p-2 ring-glass-border shadow-lg backdrop-blur-lg backdrop-saturate-150"
      style={style}
    >
      {notes.map((note) => (
        // Provenance is never subtle: badge on every note, and AI text gets its own background.
        <div
          key={note.id}
          className={cn('flex flex-col gap-1 rounded-md p-1', note.provenance !== 'human' && 'bg-provenance-llm-surface')}
        >
          <ProvenanceBadge provenance={note.provenance} />
          {note.body ? (
            <p className="line-clamp-6 text-sm whitespace-pre-wrap">{note.body}</p>
          ) : (
            <p className="line-clamp-3 text-sm text-muted-foreground">
              {note.anchors.find((a) => a.paper_id === paperId)?.quoted_text}
            </p>
          )}
        </div>
      ))}
    </Card>
  )
}
