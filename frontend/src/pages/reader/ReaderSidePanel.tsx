import type { Note, NoteKind, Paper } from '@/entities'
import type { ReaderTab } from '@/router/route'
import { ChatPanel } from '@/features/chat/ChatPanel'
import { DataPanel } from '@/features/datasets/DataPanel'
import { LensPanel } from '@/features/lenses/LensPanel'
import type { useLensReader } from '@/features/lenses/useLensReader'
import { SimilarTab } from '@/features/discovery/SimilarTab'
import { NotesPanel } from '@/features/notes/NotesPanel'
import { ReferencesTab } from '@/features/references/ReferencesTab'
import { EvidencePanel } from '@/features/evidence/EvidencePanel'
import { RightPanel } from '@/features/reader/RightPanel'
import type { NoteDraft } from '@/features/reader/selection'
import type { PdfRect } from '@/lib/coords'
import { scrollToElement, scrollToPage } from '@/features/reader/readerScroll'

const STILL_EMBEDDING = 'Still preparing full search. Until it finishes, long papers answer from keyword matches.'

type Props = {
  paperId: string
  paper: Paper | undefined
  noPdf: boolean
  tab: ReaderTab
  showTab: (next: ReaderTab) => void
  panelWidth: number
  onWidthChange: (width: number) => void
  lensReader: ReturnType<typeof useLensReader>
  notes: Note[]
  draft: NoteDraft | null
  draftColor: string
  onDraftColorChange: (color: string) => void
  activeNoteId: string | null
  wholePaperDraft: { kind: NoteKind | null } | null
  movedToNotes: boolean
  onMovedToNotesChange: (moved: boolean) => void
  onNewPaperNote: () => void
  onCancelPaperNote: () => void
  onPaperNoteDirty: (dirty: boolean) => void
  onSavePaperNote: (body: string, kind: NoteKind | null) => Promise<boolean>
  onSaveDraft: (body: string, kind?: NoteKind | null, color?: string) => Promise<boolean>
  onCancelDraft: () => void
  onAddNumber: () => void
  onSelectNote: (note: Pick<Note, 'id'>) => void
  onShowPromotedNote: (note: Note) => void
  onUpdateNote: (note: Note, body: string, kind?: NoteKind | null) => Promise<boolean>
  onColorNote: (note: Note, color: string) => Promise<boolean>
  onDeleteNote: (note: Note) => Promise<void>
  onFlashChunk: (page: number, rects: PdfRect[]) => void
}

/** The reader's right-hand panel: the Notes, Chat, Data, Similar, References, Evidence and Lens tabs. */
export function ReaderSidePanel(props: Props) {
  const { paperId, paper, noPdf, tab, showTab, panelWidth, onWidthChange, lensReader } = props
  const { notes, draft, draftColor, onDraftColorChange, activeNoteId, wholePaperDraft, movedToNotes, onMovedToNotesChange } = props
  const { onNewPaperNote, onCancelPaperNote, onPaperNoteDirty, onSavePaperNote, onSaveDraft, onCancelDraft, onAddNumber } = props
  const { onSelectNote, onShowPromotedNote, onUpdateNote, onColorNote, onDeleteNote, onFlashChunk } = props
  return (
    <RightPanel
      tab={tab}
      onTabChange={showTab}
      width={panelWidth}
      onWidthChange={onWidthChange}
      notes={
        <NotesPanel
          paperId={paperId}
          hasPdf={!noPdf}
          onCite={(source) => onFlashChunk(source.page, source.bbox ?? [])}
          hasAbstract={Boolean(paper?.abstract)}
          wholePaperDraft={wholePaperDraft}
          onNewPaperNote={onNewPaperNote}
          onCancelPaperNote={onCancelPaperNote}
          onPaperNoteDirty={onPaperNoteDirty}
          onSavePaperNote={onSavePaperNote}
          notes={notes}
          draft={draft}
          draftColor={draftColor}
          activeNoteId={activeNoteId}
          onDraftColorChange={onDraftColorChange}
          onSaveDraft={onSaveDraft}
          onCancelDraft={onCancelDraft}
          onAddNumber={onAddNumber}
          onSelectNote={onSelectNote}
          onUpdateNote={onUpdateNote}
          onColorNote={onColorNote}
          onDeleteNote={onDeleteNote}
          movedToNotes={movedToNotes}
          onPapersSaved={(saved) => onMovedToNotesChange(!saved.paper_ids.includes(paperId))}
        />
      }
      chat={
        <ChatPanel
          scope={{ kind: 'paper', id: paperId }}
          notice={paper?.status === 'embedding' ? STILL_EMBEDDING : undefined}
          // A cited passage flashes on its page, a cited abstract scrolls into view; a cited note is focused as if
          // picked in the Notes tab.
          onCite={(source) =>
            !('bbox' in source)
              ? onSelectNote({ id: source.note_id })
              : source.from_abstract
                ? scrollToElement('.paper-abstract', 'center')
                : source.replaced
                  ? scrollToPage(source.page)
                  : onFlashChunk(source.page, source.bbox ?? [])
          }
          onPromoted={onShowPromotedNote}
        />
      }
      data={<DataPanel paperId={paperId} onShowRegion={onFlashChunk} />}
      similar={<SimilarTab paperId={paperId} active={tab === 'similar'} />}
      references={<ReferencesTab paperId={paperId} active={tab === 'references'} />}
      evidence={<EvidencePanel paperId={paperId} hasPdf={!noPdf} onShowRegion={onFlashChunk} />}
      lens={<LensPanel paperId={paperId} reader={lensReader} hasPdf={!noPdf} />}
    />
  )
}
