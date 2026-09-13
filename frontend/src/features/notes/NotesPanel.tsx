import type { Note } from '@/api/client'
import { glass } from '@/components/glass'
import { cn } from '@/lib/utils'
import type { SelectionAnchor } from '../reader/selection'
import { NoteCard } from './NoteCard'
import { NoteComposer } from './NoteComposer'

type Props = {
  paperId: string
  notes: Note[]
  draft: SelectionAnchor | null
  draftColor: string
  activeNoteId: string | null
  onDraftColorChange: (hex: string) => void
  onSaveDraft: (body: string) => Promise<boolean>
  onCancelDraft: () => void
  onSelectNote: (note: Note) => void
  onUpdateNote: (note: Note, body: string) => Promise<boolean>
  onColorNote: (note: Note, hex: string) => Promise<boolean>
  onDeleteNote: (note: Note) => Promise<void>
}

// A new selection must reset the composer's text, so the draft's position is its identity.
const draftKey = (draft: SelectionAnchor) => `${draft.page}:${draft.rects.flat().join(',')}`

export function NotesPanel(props: Props) {
  const { paperId, notes, draft, activeNoteId } = props
  return (
    <aside className={cn('flex flex-col gap-3 overflow-auto border-l border-glass-border p-4', glass)} aria-label="Notes">
      {draft ? (
        <NoteComposer
          key={draftKey(draft)}
          draft={draft}
          color={props.draftColor}
          onColorChange={props.onDraftColorChange}
          onSave={props.onSaveDraft}
          onCancel={props.onCancelDraft}
        />
      ) : (
        <p className="text-sm text-muted-foreground">Select text in the paper to add a note.</p>
      )}
      {notes.map((note) => (
        <NoteCard
          key={note.id}
          note={note}
          paperId={paperId}
          active={note.id === activeNoteId}
          onSelect={() => props.onSelectNote(note)}
          onUpdate={(body) => props.onUpdateNote(note, body)}
          onColorChange={(hex) => props.onColorNote(note, hex)}
          onDelete={() => props.onDeleteNote(note)}
        />
      ))}
    </aside>
  )
}
