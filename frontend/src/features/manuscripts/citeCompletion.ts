import type { Completion, CompletionContext, CompletionResult } from '@codemirror/autocomplete'
import { EditorView } from '@codemirror/view'
import type { DeckPaper } from './deck/deckModel'

export const PAPER_DRAG_TYPE = 'application/x-paperlab-paper'

// The same shape as citeKeyAt's, but open-ended: the text before the cursor ends inside an unclosed \cite…{ key list.
const OPEN_CITE = /\\[A-Za-z]*[Cc]ite[A-Za-z]*\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^{}]*)$/

/** Where the key being typed starts, when the cursor (end of `before`) is inside a \cite… argument; else null. */
export function citeWordStart(before: string): number | null {
  if (/(?<!\\)%/.test(before)) return null // a comment
  const m = OPEN_CITE.exec(before)
  if (!m) return null
  const list = m[1]
  const word = list.slice(list.lastIndexOf(',') + 1)
  return before.length - word.trimStart().length
}

const label = (p: DeckPaper) => `${p.key} — ${[p.first_author, p.year].filter(Boolean).join(' ')}${p.first_author || p.year ? ': ' : ''}${p.title}`

/** A completion source for keys inside \cite{…}. Picking one inserts its key and calls `onCite(paperId)` (which pins it). */
export function citeSource(get: () => { papers: DeckPaper[]; onCite?: (paperId: string) => void }) {
  return (ctx: CompletionContext): CompletionResult | null => {
    const line = ctx.state.doc.lineAt(ctx.pos)
    const from = citeWordStart(line.text.slice(0, ctx.pos - line.from))
    if (from === null) return null
    const options: Completion[] = get().papers.map((p) => ({
      label: label(p),
      apply: (view, _c, a, b) => {
        view.dispatch({ changes: { from: a, to: b, insert: p.key }, selection: { anchor: a + p.key.length }, userEvent: 'input.complete' })
        get().onCite?.(p.paper_id)
      },
    }))
    return { from: line.from + from, options, filter: true, validFor: /^[^,{}]*$/ }
  }
}

/** Dropping a dragged paper pins it once; returns false so the editor still inserts the dragged text itself. */
export const paperDrop = (get: () => ((paperId: string) => void) | undefined) =>
  EditorView.domEventHandlers({
    drop: (event) => {
      const dt = event.dataTransfer
      const id = dt && Array.from(dt.types).includes(PAPER_DRAG_TYPE) ? dt.getData(PAPER_DRAG_TYPE) : ''
      if (id) get()?.(id)
      return false
    },
  })

/** Starts a drag of one paper (or one of its notes): the text to insert, plus the paper's id so the drop can pin it. */
export function startPaperDrag(e: { dataTransfer: DataTransfer | null }, paperId: string, text: string) {
  e.dataTransfer?.setData('text/plain', text)
  e.dataTransfer?.setData(PAPER_DRAG_TYPE, paperId)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}
