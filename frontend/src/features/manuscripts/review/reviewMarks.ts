import { StateEffect, StateField } from '@codemirror/state'
import { Decoration, EditorView, WidgetType, type DecorationSet } from '@codemirror/view'
import type { ReviewSentence } from '@/api/client'
import { citeThisEdit, itemTone, VERDICT_LABEL, type Mark, type Tone } from './reviewModel'

export const setReviewMarks = StateEffect.define<Mark[]>()

const TONE_RANK: Tone[] = ['bad', 'warn', 'good', 'muted'] // the sentence takes its worst verdict's tone

const label = (m: Mark) => m.items.map((i) => `${VERDICT_LABEL[i.verdict ?? ''] ?? 'Not checked'}${i.reason ? `: ${i.reason}` : ''}`).join('\n')

class AIBadge extends WidgetType {
  readonly text: string
  readonly verdict: string
  constructor(text: string, verdict: string) {
    super()
    this.text = text
    this.verdict = verdict
  }
  eq(o: AIBadge) { return o.text === this.text && o.verdict === this.verdict }
  toDOM() {
    const badge = document.createElement('span')
    badge.className = 'cm-review-badge'
    badge.title = this.text
    badge.append('⟨AI⟩')
    const verdict = document.createElement('span')
    verdict.className = 'cm-review-verdict'
    verdict.textContent = ` ${this.verdict}`
    badge.append(verdict)
    return badge
  }
}

function build(marks: Mark[], length: number): DecorationSet {
  const ranges = marks.filter((m) => m.from < m.to && m.to <= length).flatMap((m) => {
    const tone = TONE_RANK.find((t) => m.items.some((i) => itemTone(i) === t)) ?? 'muted'
    const verdict = [...new Set(m.items.map((i) => VERDICT_LABEL[i.verdict ?? ''] ?? 'Not checked'))].join(', ')
    return [
      Decoration.mark({ class: `cm-review-mark cm-review-${tone}`, attributes: { title: label(m) }, hash: m.items[0].sentence_hash }).range(m.from, m.to),
      Decoration.widget({ widget: new AIBadge(label(m), verdict), side: 1 }).range(m.to),
    ]
  })
  return Decoration.set(ranges, true)
}

const field = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, tr) {
    const marks = tr.effects.find((e) => e.is(setReviewMarks))
    return marks ? build(marks.value, tr.state.doc.length) : value.map(tr.changes)
  },
  provide: (f) => EditorView.decorations.from(f),
})

const theme = EditorView.baseTheme({
  '.cm-review-mark': { textDecoration: 'underline dotted 2px', textUnderlineOffset: '3px' },
  '.cm-review-good': { textDecorationColor: 'var(--review-good, #16a34a)' },
  '.cm-review-warn': { textDecorationColor: 'var(--review-warn, #d97706)' },
  '.cm-review-bad': { textDecorationColor: 'var(--destructive)' },
  '.cm-review-muted': { textDecorationColor: 'var(--muted-foreground)' },
  '.cm-review-badge': { fontSize: '0.75em', margin: '0 2px', padding: '0 3px', borderRadius: '3px', backgroundColor: 'var(--provenance-llm-surface)', color: 'var(--provenance-llm)' },
})

export const reviewExtension = () => [field, theme]

export type ReviewHandle = {
  setMarks: (marks: Mark[]) => void
  spanOf: (hash: string) => { start: number; end: number } | null
  /** Selects the sentence and focuses the editor; a sentence without a mark is located afresh. */
  reveal: (hash: string) => void
  selection: () => { from: number; to: number } | null
  /** The cursor (the selection's head), UTF-16. */
  cursor: () => number
  /** Whether the sentence is still in the text as it is now (asks the server to locate it afresh). */
  canCite: (hash: string) => Promise<boolean>
  applyCite: (hash: string, key: string) => Promise<'ok' | 'changed'>
}

/** The editor's side of the reviewer. `locate` finds the sentences of the text as it is now (UTF-16 offsets). */
export function reviewHandle(view: EditorView, locate: (text: string) => Promise<ReviewSentence[]>): ReviewHandle {
  const spanOf: ReviewHandle['spanOf'] = (hash) => {
    let found: { start: number; end: number } | null = null
    view.state.field(field).between(0, view.state.doc.length, (from, to, deco) => {
      if (deco.spec.hash === hash && !found) found = { start: from, end: to }
    })
    return found
  }
  // The sentence in the text as it is now; null when it is gone, or the text moved on while we asked.
  const find = async (hash: string) => {
    const sent = view.state.doc.toString()
    const span = (await locate(sent)).find((s) => s.hash === hash)
    return span && view.state.doc.toString() === sent ? { sent, span } : null
  }
  const select = (span: { start: number; end: number }) => {
    view.dispatch({ selection: { anchor: span.start, head: span.end }, effects: EditorView.scrollIntoView(span.start, { y: 'center' }) })
    view.focus()
  }
  return {
    setMarks: (marks) => view.dispatch({ effects: setReviewMarks.of(marks) }),
    spanOf,
    reveal: (hash) => {
      const span = spanOf(hash)
      if (span) select(span)
      else void find(hash).then((f) => f && select(f.span), () => {}) // a section review's sentence carries no mark
    },
    cursor: () => view.state.selection.main.head,
    selection: () => {
      const { from, to } = view.state.selection.main
      return from === to ? null : { from, to }
    },
    async canCite(hash) {
      return !!(await find(hash))
    },
    async applyCite(hash, key) {
      const found = await find(hash)
      if (!found) return 'changed'
      const { sent, span } = found
      const { from, insert } = citeThisEdit(sent, span, key)
      view.dispatch({ changes: { from, insert }, selection: { anchor: from + insert.length }, userEvent: 'input.paste', scrollIntoView: true })
      return 'ok'
    },
  }
}
