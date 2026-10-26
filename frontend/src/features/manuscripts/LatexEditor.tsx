import { HighlightStyle, StreamLanguage, syntaxHighlighting } from '@codemirror/language'
import { tags } from '@lezer/highlight'
import { stex } from '@codemirror/legacy-modes/mode/stex'
import { Annotation, Compartment, RangeSetBuilder, Transaction } from '@codemirror/state'
import { EditorView, GutterMarker, gutter, keymap } from '@codemirror/view'
import { basicSetup } from 'codemirror'
import { useEffect, useRef } from 'react'

type LineError = { line: number; message: string }
type Props = {
  value: string
  onChange: (text: string) => void
  /** Compile errors for this file: a red dot in the gutter, the message on hover. */
  errors: LineError[]
  onSave: () => void
  /** Move the cursor to this line; a new `n` jumps again to the same line. */
  jumpTo?: { line: number; n: number } | null
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
const theme = EditorView.theme({
  '&': { height: '100%', fontSize: '13px', color: 'var(--foreground)', backgroundColor: 'var(--background)' },
  '.cm-scroller': { overflow: 'auto', fontFamily: 'var(--font-mono, ui-monospace, monospace)' },
  '.cm-content': { caretColor: 'var(--foreground)' },
  '.cm-cursor': { borderLeftColor: 'var(--foreground)' },
  '.cm-gutters': { backgroundColor: 'var(--muted)', color: 'var(--muted-foreground)', border: 'none' },
  '.cm-activeLine, .cm-activeLineGutter': { backgroundColor: 'var(--accent)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': { backgroundColor: 'color-mix(in srgb, var(--primary) 30%, transparent)' },
  '&.cm-focused': { outline: '2px solid var(--ring)', outlineOffset: '-2px' },
})

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
export function LatexEditor({ value, onChange, errors, onSave, jumpTo, label = 'LaTeX source' }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const errorSlot = useRef(new Compartment())
  // The view is built once; callbacks go through a ref so it never holds a stale one.
  const latest = useRef({ onChange, onSave })
  latest.current = { onChange, onSave }

  useEffect(() => {
    const editor = new EditorView({
      doc: value,
      parent: host.current!,
      extensions: [
        basicSetup,
        StreamLanguage.define(stex),
        EditorView.lineWrapping,
        theme,
        highlight,
        EditorView.contentAttributes.of({ 'aria-label': label }),
        errorSlot.current.of(errorGutter(errors)),
        keymap.of([{ key: 'Mod-s', run: () => (latest.current.onSave(), true) }]),
        EditorView.updateListener.of((u) => {
          if (u.docChanged && !u.transactions.some((t) => t.annotation(FromHost))) latest.current.onChange(u.state.doc.toString())
        }),
      ],
    })
    view.current = editor
    return () => editor.destroy()
    // ponytail: built once per mount; the page remounts it per file, and the effects below carry later changes.
  }, [])

  useEffect(() => {
    const editor = view.current!
    if (editor.state.doc.toString() === value) return
    editor.dispatch({
      changes: { from: 0, to: editor.state.doc.length, insert: value },
      annotations: [FromHost.of(true), Transaction.addToHistory.of(false)],
    })
  }, [value])

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
