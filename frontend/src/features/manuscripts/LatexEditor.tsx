import { HighlightStyle, StreamLanguage, syntaxHighlighting } from '@codemirror/language'
import { tags } from '@lezer/highlight'
import { stex } from '@codemirror/legacy-modes/mode/stex'
import { Annotation, Compartment, EditorState, Prec, RangeSetBuilder, Transaction } from '@codemirror/state'
import { EditorView, GutterMarker, gutter, keymap } from '@codemirror/view'
import { basicSetup } from 'codemirror'
import { useEffect, useRef, useState } from 'react'
import { autocompletion } from '@codemirror/autocomplete'
import { citeKeyAt } from './deck/citeKeyAt'
import type { DeckPaper } from './deck/deckModel'
import { citeSource, paperDrop } from './citeCompletion'
import { reviewExtension, reviewHandle, type ReviewHandle } from './review/reviewMarks'
import type { ReviewSentence } from '@/api/client'
import { ownLine, type PreambleEdit } from './results/insertBlock'

type LineError = { line: number; message: string }
type Props = {
  value: string
  onChange: (text: string) => void
  /** Compile errors for this file: a red dot in the gutter, the message on hover. */
  errors: LineError[]
  onSave: () => void
  /** Move the cursor to this line; a new `n` jumps again to the same line. */
  jumpTo?: { line: number; n: number } | null
  /** The cursor's line (1-based), whenever it moves to another line. */
  onCursor?: (line: number) => void
  /** Mod-Alt-Up / Down: the previous / next section. */
  onSectionStep?: (step: -1 | 1) => void
  /** Mod-Alt-P: show the cursor's line in the PDF. */
  onShowInPdf?: (line: number) => void
  /** Mod-Alt-K with the cursor in a \cite{…} key list: the key under it. */
  onCiteKey?: (key: string) => void
  /** Mod-E: find evidence for the selection, or the sentence at the cursor (from, to are equal then), in the editor's own text. */
  onFindEvidence?: (doc: string, from: number, to: number) => void
  /** Hands the page a way to insert text at the cursor (the last one when unfocused; the end if it never moved) as a normal edit, then focus the editor. */
  registerInsert?: (insert: ((text: string, block?: boolean, preamble?: PreambleEdit) => void) | null) => void
  /** Hands out a way to run Find evidence on the last cursor; it returns false until the cursor has been placed. */
  registerFindEvidence?: (run: (() => boolean) | null) => void
  /** Hands out the reviewer's hold on the editor: marks, sentence spans and Cite this. */
  registerReview?: (handle: ReviewHandle | null) => void
  /** Finds the sentences of a text (UTF-16 offsets); Cite this uses it on the text as it is at the click. */
  reviewLocate?: (text: string) => Promise<ReviewSentence[]>
  /** The library's papers, offered as keys inside \cite{…}. */
  citeOptions?: DeckPaper[]
  /** A key was picked from the list, or a dragged paper was dropped: pin this paper. */
  onCite?: (paperId: string) => void
  label?: string
}

class ErrorMarker extends GutterMarker {
  readonly message: string
  constructor(message: string) {
    super()
    this.message = message
  }
  toDOM() {
    const dot = document.createElement('span')
    dot.textContent = '●'
    dot.title = this.message
    dot.setAttribute('role', 'img')
    dot.setAttribute('aria-label', `Error: ${this.message}`)
    dot.style.color = 'var(--destructive)'
    return dot
  }
}

const errorGutter = (errors: LineError[]) =>
  gutter({
    class: 'cm-error-gutter',
    markers: (view) => {
      const builder = new RangeSetBuilder<GutterMarker>()
      const lines = view.state.doc.lines
      const rows = errors.filter((e) => e.line >= 1 && e.line <= lines).sort((a, b) => a.line - b.line)
      for (const e of rows) builder.add(view.state.doc.line(e.line).from, view.state.doc.line(e.line).from, new ErrorMarker(e.message))
      return builder.finish()
    },
  })

// The app's own colour tokens, so the editor follows light and dark with the rest of the window (see MASTER.md).
// `dark` tells CodeMirror which base theme to sit on; the colours themselves come from the tokens.
export const latexTheme = (dark: boolean) =>
  EditorView.theme(
    {
      '&': { height: '100%', fontSize: '13px', color: 'var(--foreground)', backgroundColor: 'var(--background)' },
      '.cm-scroller': { overflow: 'auto', fontFamily: 'var(--font-mono, ui-monospace, monospace)' },
      '.cm-content': { caretColor: 'var(--foreground)' },
      '.cm-cursor': { borderLeftColor: 'var(--foreground)' },
      '.cm-gutters': { backgroundColor: 'var(--muted)', color: 'var(--muted-foreground)', border: 'none' },
      // Translucent, so a selection inside the current line stays visible.
      '.cm-activeLine, .cm-activeLineGutter': { backgroundColor: 'color-mix(in oklab, var(--accent) 40%, transparent)' },
      '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': { backgroundColor: 'color-mix(in srgb, var(--primary) 30%, transparent)' },
      '&.cm-focused': { outline: '2px solid var(--ring)', outlineOffset: '-2px' },
    },
    { dark },
  )

/** Whether the app is in dark mode: ThemeProvider toggles the `dark` class on the root element. */
function useAppIsDark() {
  const root = document.documentElement
  const [dark, setDark] = useState(() => root.classList.contains('dark'))
  useEffect(() => {
    const observer = new MutationObserver(() => setDark(root.classList.contains('dark')))
    observer.observe(root, { attributes: true, attributeFilter: ['class'] })
    setDark(root.classList.contains('dark'))
    return () => observer.disconnect()
  }, [root])
  return dark
}

const highlight = syntaxHighlighting(
  HighlightStyle.define([
    { tag: tags.comment, color: 'var(--muted-foreground)', fontStyle: 'italic' },
    { tag: [tags.keyword, tags.tagName, tags.atom], color: 'var(--primary)' },
    { tag: [tags.string, tags.number, tags.meta], color: 'color-mix(in srgb, var(--primary) 55%, var(--foreground))' },
    { tag: [tags.bracket, tags.punctuation], color: 'var(--muted-foreground)' },
    { tag: tags.invalid, color: 'var(--destructive)' },
  ]),
)

// Marks a change the host made (a new `value`), so it is not reported back as an edit and never enters undo history.
const FromHost = Annotation.define<boolean>()

/** CodeMirror 6 with LaTeX highlighting, as one controlled-ish component: `value` in, `onChange` out. */
export function LatexEditor({ value, onChange, errors, onSave, jumpTo, onCursor, onSectionStep, onShowInPdf, onCiteKey, onFindEvidence, registerInsert, registerFindEvidence, registerReview, reviewLocate, citeOptions, onCite, label = 'LaTeX source' }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const errorSlot = useRef(new Compartment())
  const themeSlot = useRef(new Compartment())
  const dark = useAppIsDark()
  // The view is built once; callbacks go through a ref so it never holds a stale one.
  const latest = useRef({ citeOptions, onCite, onChange, onSave, onCursor, onSectionStep, onShowInPdf, onCiteKey, onFindEvidence, registerInsert, registerFindEvidence, registerReview, reviewLocate })
  latest.current = { citeOptions, onCite, onChange, onSave, onCursor, onSectionStep, onShowInPdf, onCiteKey, onFindEvidence, registerInsert, registerFindEvidence, registerReview, reviewLocate }
  const moved = useRef(false) // whether the cursor was ever placed; if not, an insert goes to the end
  const cursorLine = useRef(0)

  useEffect(() => {
    const editor = new EditorView({
      doc: value,
      parent: host.current!,
      extensions: [
        basicSetup,
        autocompletion({ override: [citeSource(() => ({ papers: latest.current.citeOptions ?? [], onCite: latest.current.onCite }))], icons: false }),
        paperDrop(() => latest.current.onCite),
        StreamLanguage.define(stex),
        EditorView.lineWrapping,
        themeSlot.current.of(latexTheme(dark)),
        highlight,
        reviewExtension(),
        EditorView.contentAttributes.of({ 'aria-label': label }),
        errorSlot.current.of(errorGutter(errors)),
        keymap.of([{ key: 'Mod-s', run: () => (latest.current.onSave(), true) }]),
        // Mod-Alt, not Alt: CodeMirror's own Alt-Up / Down move the line. High precedence so basicSetup never sees these.
        Prec.high(keymap.of([
          { key: 'Mod-Alt-ArrowUp', run: () => (latest.current.onSectionStep?.(-1), true) },
          { key: 'Mod-Alt-ArrowDown', run: () => (latest.current.onSectionStep?.(1), true) },
          {
            key: 'Mod-Alt-k',
            run: (v) => {
              const head = v.state.selection.main.head
              const line = v.state.doc.lineAt(head)
              const key = citeKeyAt(line.text, head - line.from)
              if (key) latest.current.onCiteKey?.(key)
              return !!key
            },
          },
          // Mod-e is free: CodeMirror binds only Ctrl-e (line end), and only on macOS, where Mod is Cmd. Taken high anyway.
          { key: 'Mod-e', run: (v) => { const { from, to } = v.state.selection.main; latest.current.onFindEvidence?.(v.state.doc.toString(), from, to); return true } },
          { key: 'Mod-Alt-p', run: (v) => (latest.current.onShowInPdf?.(v.state.doc.lineAt(v.state.selection.main.head).number), true) },
        ])),
        EditorView.updateListener.of((u) => {
          if (u.selectionSet) moved.current = true
          if (u.selectionSet || u.docChanged) {
            const line = u.state.doc.lineAt(u.state.selection.main.head).number
            if (line !== cursorLine.current) { cursorLine.current = line; latest.current.onCursor?.(line) }
          }
          if (u.docChanged && !u.transactions.some((t) => t.annotation(FromHost))) latest.current.onChange(u.state.doc.toString())
        }),
      ],
    })
    view.current = editor
    latest.current.registerFindEvidence?.(() => {
      if (!moved.current) return false
      const { from, to } = editor.state.selection.main
      latest.current.onFindEvidence?.(editor.state.doc.toString(), from, to)
      return true
    })
    latest.current.registerInsert?.((text, block, preamble) => {
      const at = moved.current ? editor.state.selection.main.head : editor.state.doc.length // never over a selection
      // A comment (an AI note, D118) gets lines of its own: mid-line it would comment out the rest of the researcher's
      // line, and it always ends with a line break so the cursor (placed after it) is never left inside the comment.
      const own = text.startsWith('%')
      const line = editor.state.doc.lineAt(at)
      // A block (a table or figure) gets lines of its own too, but needs no extra break when it lands at a line end.
      const insert = block ? ownLine(text, at === line.from, at === line.to) : own ? `${at > line.from ? '\n' : ''}${text}\n` : text
      // The preamble lines (positions in the document as it is now) and the text go in one transaction: atomic and one undo.
      const pre = preamble ? [{ from: editor.state.doc.line(preamble.line).from + preamble.col, insert: preamble.text }] : []
      const changes = editor.state.changes([...pre, { from: at, insert }])
      editor.dispatch({
        changes,
        selection: { anchor: changes.mapPos(at, 1) },
        scrollIntoView: true,
        userEvent: 'input.paste', // a normal edit: reported to onChange (autosave) and undoable
      })
      editor.focus()
    })
    latest.current.registerReview?.(reviewHandle(editor, (t) => latest.current.reviewLocate?.(t) ?? Promise.resolve([])))
    return () => { latest.current.registerReview?.(null); latest.current.registerInsert?.(null); latest.current.registerFindEvidence?.(null); editor.destroy() }
    // ponytail: built once per mount; the page remounts it per file, and the effects below carry later changes.
  }, [])

  useEffect(() => {
    const editor = view.current!
    if (editor.state.doc.toString() === value) return
    // Keep the cursor on its line and column (clamped); a line that is gone puts it at the end.
    const head = editor.state.selection.main.head
    const old = editor.state.doc.lineAt(head)
    const next = EditorState.create({ doc: value }).doc
    const anchor = old.number > next.lines ? next.length : Math.min(next.line(old.number).from + (head - old.from), next.line(old.number).to)
    editor.dispatch({
      changes: { from: 0, to: editor.state.doc.length, insert: value },
      selection: { anchor },
      annotations: [FromHost.of(true), Transaction.addToHistory.of(false)],
    })
  }, [value])

  useEffect(() => {
    view.current!.dispatch({ effects: themeSlot.current.reconfigure(latexTheme(dark)) })
  }, [dark])

  useEffect(() => {
    view.current!.dispatch({ effects: errorSlot.current.reconfigure(errorGutter(errors)) })
  }, [errors])

  useEffect(() => {
    const editor = view.current!
    if (!jumpTo || jumpTo.line < 1 || jumpTo.line > editor.state.doc.lines) return
    const at = editor.state.doc.line(jumpTo.line).from
    editor.dispatch({ selection: { anchor: at }, effects: EditorView.scrollIntoView(at, { y: 'center' }) })
    editor.focus()
  }, [jumpTo])

  return <div ref={host} className="h-full min-h-0 overflow-hidden" />
}
