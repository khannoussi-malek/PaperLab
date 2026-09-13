import type { CSSProperties } from 'react'
import type { Note } from '@/api/client'
import { NoteCard } from './NoteCard'

type Props = {
  notes: Note[]
  paperId: string
  /** Position inside the page overlay, in CSS pixels of the page. */
  style: CSSProperties
  /** A note to open straight in edit mode. */
  editNoteId?: string
  onPointerEnter: () => void
  onPointerLeave: () => void
  onEditingChange: (noteId: string, editing: boolean) => void
  onUpdate: (note: Note, body: string) => Promise<boolean>
  onColorChange: (note: Note, hex: string) => Promise<boolean>
  onDelete: (note: Note) => Promise<void>
}

/**
 * The notes under the pointer, manageable in place. It lives in the page overlay, which ignores the mouse so
 * text selection keeps working; the card takes pointer events back for itself.
 */
export function NoteHoverCard({ notes, paperId, style, editNoteId, ...handlers }: Props) {
  return (
    <div
      className="note-hover-card pointer-events-auto absolute z-10 flex w-80 flex-col gap-2"
      style={style}
      onMouseEnter={handlers.onPointerEnter}
      onMouseLeave={handlers.onPointerLeave}
    >
      {notes.map((note) => (
        <NoteCard
          // Remount on an edit request, so `startEditing` also applies to a card that is already showing.
          key={`${note.id}:${note.id === editNoteId}`}
          note={note}
          paperId={paperId}
          compact
          startEditing={note.id === editNoteId}
          onUpdate={(body) => handlers.onUpdate(note, body)}
          onColorChange={(hex) => handlers.onColorChange(note, hex)}
          onDelete={() => handlers.onDelete(note)}
          onEditingChange={handlers.onEditingChange}
          // Blur earns its place here: the card floats over the PDF text it would otherwise clash with.
          className="shadow-lg backdrop-blur-lg backdrop-saturate-150"
        />
      ))}
    </div>
  )
}
