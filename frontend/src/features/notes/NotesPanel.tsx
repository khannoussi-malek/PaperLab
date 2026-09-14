import { Check, Sparkles, UserRound } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { Note } from '@/api/client'
import { cn } from '@/lib/utils'
import { pressable } from '@/components/motion'
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

const isHuman = (note: Note) => note.provenance === 'human'

export function NotesPanel(props: Props) {
  const { paperId, notes, draft, activeNoteId } = props
  const [show, setShow] = useState({ human: true, ai: true })
  const humanCount = notes.filter(isHuman).length
  // An edited AI note is still AI: its badge says "AI · edited".
  const shown = notes.filter((note) => (isHuman(note) ? show.human : show.ai))
  return (
    // RightPanel draws the glass and the border; blur inside blur looks muddy.
    <aside className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4" aria-label="Notes">
      {/* Filters the list only: every highlight stays on the paper. */}
      <div role="group" aria-label="Show notes from" className="flex flex-wrap items-center gap-2">
        <FilterChip
          label="You"
          count={humanCount}
          icon={<UserRound aria-hidden />}
          pressed={show.human}
          pressedClass="bg-secondary text-foreground ring-input"
          onToggle={() => setShow({ ...show, human: !show.human })}
        />
        <FilterChip
          label="AI"
          count={notes.length - humanCount}
          icon={<Sparkles aria-hidden />}
          pressed={show.ai}
          pressedClass="bg-provenance-llm-surface text-provenance-llm ring-provenance-llm/40"
          onToggle={() => setShow({ ...show, ai: !show.ai })}
        />
      </div>
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
      {notes.length > 0 && shown.length === 0 && (
        <p className="text-sm text-muted-foreground">No notes match these filters.</p>
      )}
      {shown.map((note) => (
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

type FilterProps = {
  label: string
  count: number
  icon: ReactNode
  pressed: boolean
  /** Fill and text colours when on, matching the note's provenance badge. */
  pressedClass: string
  onToggle: () => void
}

/** A filter chip. On: filled in its provenance colours, with a check. Off: its own icon, outlined and muted. */
function FilterChip({ label, count, icon, pressed, pressedClass, onToggle }: FilterProps) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      aria-label={`${label} (${count})`}
      onClick={onToggle}
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium ring-1 transition-[color,background-color,box-shadow,scale] duration-150 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-3.5',
        pressable,
        pressed ? pressedClass : 'text-muted-foreground ring-border ring-inset hover:bg-muted hover:text-foreground',
      )}
    >
      {pressed ? <Check aria-hidden /> : icon}
      {label}
      <span className={cn('min-w-4 rounded-full px-1 text-center tabular-nums', pressed ? 'bg-background/70' : 'bg-muted')}>
        {count}
      </span>
    </button>
  )
}
