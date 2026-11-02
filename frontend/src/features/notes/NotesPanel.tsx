import { Check, FilePen, Sparkles, UserRound } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { ChatSource, Note, NoteKind } from '@/api/client'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { pressable } from '@/components/motion'
import { notesHref } from '@/lib/route'
import type { NoteDraft } from '../reader/selection'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { KIND_LABEL, matchesKind } from './noteKinds'
import { NoteCheck } from '../checks/NoteCheck'
import { NoteCard } from './NoteCard'
import { NoteComposer, PlainNoteComposer } from './NoteComposer'
import { SuggestedNotes } from './SuggestedNotes'

type Props = {
  paperId: string
  /** False for a paper saved without its PDF: notes quote its abstract, or are written with no quote. */
  hasPdf?: boolean
  /** Whether that paper has an abstract to select from. */
  hasAbstract?: boolean
  /** The whole-paper composer is open (with this kind preset), or not. */
  wholePaperDraft: { kind: NoteKind | null } | null
  onNewPaperNote: () => void
  onCancelPaperNote: () => void
  /** Saves a note with no quote. */
  onSavePaperNote: (body: string, kind: NoteKind | null) => Promise<boolean>
  notes: Note[]
  draft: NoteDraft | null
  draftColor: string
  activeNoteId: string | null
  onDraftColorChange: (hex: string) => void
  onSaveDraft: (body: string, kind: NoteKind | null) => Promise<boolean>
  onCancelDraft: () => void
  onAddNumber: () => void
  onSelectNote: (note: Note) => void
  onUpdateNote: (note: Note, body: string, kind?: NoteKind | null) => Promise<boolean>
  onColorNote: (note: Note, hex: string) => Promise<boolean>
  onDeleteNote: (note: Note) => Promise<void>
  /** A Papers save just took a note off this paper: say where it went. */
  movedToNotes: boolean
  onPapersSaved: (note: Note) => void
  /** Shows a passage a check cites. */
  onCite: (source: ChatSource) => void
}

// A new selection must reset the composer's text, so the draft's position and words are its identity: an abstract
// selection has no position.
const draftKey = (draft: NoteDraft) => `${draft.page}:${draft.rects.flat().join(',')}:${draft.quotedText}`

const isHuman = (note: Note) => note.provenance === 'human'

export function NotesPanel(props: Props) {
  const { paperId, notes, draft, activeNoteId } = props
  const [show, setShow] = useState({ human: true, ai: true })
  const [kind, setKind] = useState<'all' | 'plain' | NoteKind>('all')
  const humanCount = notes.filter(isHuman).length
  // An edited AI note is still AI: its badge says "AI · edited".
  const shown = notes.filter((note) => (isHuman(note) ? show.human : show.ai) && matchesKind(note, kind))
  return (
    // RightPanel draws the glass and the border; blur inside blur looks muddy.
    <aside className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4" aria-label="Notes">
      {props.movedToNotes && (
        <p role="status" className="moved-notice rounded-lg bg-muted px-3 py-2 text-sm">
          Moved to{' '}
          <a href={notesHref()} className="text-primary hover:underline">
            Notes
          </a>
        </p>
      )}
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
        <Select value={kind} onValueChange={(next) => setKind(next as typeof kind)}>
          <SelectTrigger size="sm" aria-label="Kind">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All kinds</SelectItem>
            {Object.entries(KIND_LABEL).map(([k, label]) => (
              <SelectItem key={k} value={k}>
                {label}
              </SelectItem>
            ))}
            <SelectItem value="plain">Plain notes</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {props.hasPdf !== false && !props.wholePaperDraft && (
        <div className="flex flex-col gap-1">
          {!draft && (
            <p className="text-sm text-muted-foreground">Select text in the paper to add a note, or</p>
          )}
          <Button type="button" variant="ghost" size="sm" className="self-start" onClick={props.onNewPaperNote}>
            <FilePen aria-hidden />
            New note on this paper
          </Button>
        </div>
      )}
      {props.wholePaperDraft ? (
        <PlainNoteComposer
          key={props.wholePaperDraft.kind ?? 'none'}
          initialKind={props.wholePaperDraft.kind}
          onSave={props.onSavePaperNote}
          onCancel={props.onCancelPaperNote}
        />
      ) : draft ? (
        <NoteComposer
          key={draftKey(draft)}
          draft={draft}
          color={props.draftColor}
          onColorChange={props.onDraftColorChange}
          onSave={props.onSaveDraft}
          onCancel={props.onCancelDraft}
          onAddNumber={props.onAddNumber}
        />
      ) : props.hasPdf === false ? (
        <>
          <p className="text-sm text-muted-foreground">
            {props.hasAbstract ? 'Select text in the abstract, or write a note.' : 'Write a note.'}
          </p>
          <PlainNoteComposer onSave={props.onSavePaperNote} />
        </>
      ) : null}
      <SuggestedNotes paperId={paperId} hasPdf={props.hasPdf} />
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
          onUpdate={(body, k) => props.onUpdateNote(note, body, k)}
          editKind
          onColorChange={(hex) => props.onColorNote(note, hex)}
          onDelete={() => props.onDeleteNote(note)}
          onPapersSaved={props.onPapersSaved}
          check={<NoteCheck note={note} paperId={paperId} onCite={props.onCite} />}
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
