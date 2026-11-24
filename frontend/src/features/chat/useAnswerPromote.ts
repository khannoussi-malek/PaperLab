import { useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'
import type { ChatAnswer as SavedAnswer, Note } from '@/entities'
import { usePromoteNote } from '@/services/queries'
import { readAnswerSelection } from './answerSelection'
import { promoteInPart } from './noteBlocks'
import { promoteErrorMessage, type PromoteDraft } from './promote'
import { saveButtonPosition } from './saveButton'

type Promote = { outputId: string; draft: PromoteDraft; style: CSSProperties }

/** Selecting text in a saved answer offers "Save as note": tracks the live selection and saves its draft. */
export function useAnswerPromote({
  answers,
  rootRef,
  onPromoted,
}: {
  answers: SavedAnswer[]
  rootRef: RefObject<HTMLDivElement | null>
  onPromoted: (note: Note) => void
}) {
  const [promote, setPromote] = useState<Promote | null>(null)
  const [promoteError, setPromoteError] = useState<string | null>(null)
  const promoteNote = usePromoteNote()

  function captureSelection() {
    const selected = readAnswerSelection()
    const answer = answers.find((a) => a.id === selected?.outputId)
    const draft = selected && answer && promoteInPart(answer.content, answer.sources, selected.anchor, selected.focus)
    const box = rootRef.current?.getBoundingClientRect()
    if (!selected || !draft || !box) {
      setPromote(null)
      setPromoteError(null)
      return
    }
    // Only a genuinely different selection retires a shown error: a recapture of the *same* selection (a resize, or
    // any other re-run of this function) must not silently clear an error the user hasn't acted on yet.
    if (promote?.outputId !== selected.outputId || promote?.draft.body !== draft.body) setPromoteError(null)
    setPromote({ outputId: selected.outputId, draft, style: saveButtonPosition(selected.rect, box) })
  }

  async function saveAsNote() {
    if (!promote || promoteNote.isPending) return
    const { outputId, draft } = promote
    try {
      const note = await promoteNote.mutateAsync({ output_id: outputId, body: draft.body, chunk_ids: draft.chunkIds })
      setPromote(null)
      window.getSelection()?.removeAllRanges()
      onPromoted(note)
    } catch (e) {
      // The button (and selection) stay up: the message sits right next to it, and the user can retry.
      setPromoteError(promoteErrorMessage(e))
    }
  }

  // The selection can change without a mouseup: dragging still fires this repeatedly, and so does
  // Shift+Arrow. Re-running the full capture (not just hiding on collapse) keeps the draft live, not stale.
  useEffect(() => {
    document.addEventListener('selectionchange', captureSelection)
    return () => document.removeEventListener('selectionchange', captureSelection)
  })

  // The freshest captureSelection, for the ResizeObserver below: observing must start exactly once (`observe()`
  // itself fires one immediate callback, so re-subscribing on every render would re-fire it every render too, right
  // after any state change -- including the one that had just set an error, clearing it straight back out).
  const captureSelectionRef = useRef(captureSelection)
  useEffect(() => {
    captureSelectionRef.current = captureSelection
  })

  // The panel (or the split it sits in) can change size from under an open selection: a drag on the resize handle,
  // or coming back to a tab that was hidden. Re-measuring keeps the button under its selection either way.
  useEffect(() => {
    const node = rootRef.current
    if (!node) return
    const observer = new ResizeObserver(() => captureSelectionRef.current())
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return {
    promote,
    promoteError,
    savePending: promoteNote.isPending,
    captureSelection,
    saveAsNote,
    hidePromote: () => setPromote(null),
  }
}
