import { useRef, useState } from 'react'
import type { Note, NoteKind } from '@/entities'
import { useNoteMutations } from '@/services/queries'
import { browserStorage, loadLastColor, saveLastColor } from '@/components/highlightColors'
import type { NoteDraft, SelectionAnchor } from '@/features/reader/selection'

export const SAVE_FIRST = 'Save or cancel the note you are writing first.'

type Options = {
  paperId: string
  noPdf: boolean
  /** Runs a mutation; failures show in the alert instead of throwing. */
  attempt: (action: () => Promise<unknown>) => Promise<boolean>
  setError: (message: string | null | ((e: string | null) => string | null)) => void
}

/** The note composers (the selection draft, the whole-paper note and the number dialog) and the note mutations behind them. */
export function useNoteComposer({ paperId, noPdf, attempt, setError }: Options) {
  const mutations = useNoteMutations()
  const [draft, setDraft] = useState<NoteDraft | null>(null)
  const [wholePaperDraft, setWholePaperDraft] = useState<{ kind: NoteKind | null } | null>(null)
  const [numberDraft, setNumberDraft] = useState<SelectionAnchor | null>(null)
  const [draftColor, setDraftColor] = useState(() => loadLastColor(browserStorage()))
  // A Papers save took a note off this paper; it stays said until a save keeps one here (Spec note 17).
  const [movedToNotes, setMovedToNotes] = useState(false)
  const typedPaperNote = useRef(false) // the whole-paper composer holds text the reader typed
  // A selection or figure box never discards it; one that would is told to wait (an empty or template-only composer is replaced).
  const blockedByTypedNote = () => {
    if (typedPaperNote.current) setError(SAVE_FIRST)
    return typedPaperNote.current
  }

  async function saveDraft(body: string, kind: NoteKind | null = null, color: string = draftColor): Promise<boolean> {
    if (!draft) return false
    if (draft.figure) {
      const figure = { paper_id: paperId, page: draft.page, region: draft.rects[0], body, color }
      const done = await attempt(() => mutations.createFigure.mutateAsync(figure))
      if (done) {
        saveLastColor(browserStorage(), color)
        setDraft(null)
      }
      return done
    }
    const kindField = kind ? { kind } : {}
    // A paper without a PDF has no page to anchor on: the note goes on the paper, its body led by the abstract's words.
    const note = noPdf
      ? { body, color, paper_id: paperId, quote: draft.quotedText, ...kindField }
      : { body, color, anchor: { paper_id: paperId, page: draft.page, bbox: draft.rects, quoted_text: draft.quotedText }, ...kindField }
    const saved = await attempt(() => mutations.create.mutateAsync(note))
    if (saved) {
      saveLastColor(browserStorage(), color)
      setDraft(null)
      window.getSelection()?.removeAllRanges()
    }
    return saved
  }

  async function savePaperNote(body: string, kind: NoteKind | null): Promise<boolean> {
    const saved = await attempt(() =>
      mutations.create.mutateAsync({ body, color: draftColor, paper_id: paperId, ...(kind ? { kind } : {}) }),
    )
    if (saved) setWholePaperDraft(null) // closes one Write it or New note opened; a no-PDF paper's own composer is not a draft
    return saved
  }

  function newPaperNote() {
    setDraft(null)
    setWholePaperDraft({ kind: null })
  }

  /** The whole-paper composer reports whether it holds typed text, so a selection can't discard it. */
  function paperNoteDirty(dirty: boolean) {
    typedPaperNote.current = dirty && wholePaperDraft !== null // a no-PDF paper's own composer is no draft
    if (!dirty) setError((e) => (e === SAVE_FIRST ? null : e))
  }

  async function highlightDraft(color: string) {
    setDraftColor(color)
    await saveDraft('', null, color)
  }

  const updateNoteBody = (note: Note, body: string, kind?: NoteKind | null) =>
    attempt(() => mutations.update.mutateAsync({ id: note.id, body, ...(kind === undefined ? {} : { kind }) }))

  const recolorNote = (note: Note, color: string) =>
    attempt(() => mutations.update.mutateAsync({ id: note.id, color }))

  async function deleteNote(note: Note) {
    if (!window.confirm('Delete this note?')) return
    await attempt(() => mutations.remove.mutateAsync(note.id))
  }

  function focusComposer() {
    // After the menu has finished closing, or its focus handling takes focus straight back.
    window.setTimeout(() => document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Note"]')?.focus())
  }

  /** Both entry points (the draft menu and the composer) open the dialog on the pending selection. */
  function addNumberFromDraft() {
    setNumberDraft(draft)
  }

  return {
    draft,
    setDraft,
    wholePaperDraft,
    setWholePaperDraft,
    numberDraft,
    setNumberDraft,
    draftColor,
    setDraftColor,
    movedToNotes,
    setMovedToNotes,
    blockedByTypedNote,
    saveDraft,
    savePaperNote,
    newPaperNote,
    paperNoteDirty,
    highlightDraft,
    updateNoteBody,
    recolorNote,
    deleteNote,
    focusComposer,
    addNumberFromDraft,
  }
}
