// @vitest-environment jsdom
import { render } from '@testing-library/react'
import { completionStatus, currentCompletions, acceptCompletion, startCompletion } from '@codemirror/autocomplete'
import { EditorView } from '@codemirror/view'
import { expect, test, vi } from 'vitest'
import { LatexEditor } from './LatexEditor'
import type { DeckPaper } from './deck/deckModel'

const paper = (o: Partial<DeckPaper>): DeckPaper =>
  ({ paper_id: 'p1', key: 'lewis2020', title: 'Retrieval-augmented generation', first_author: 'Lewis', year: 2020, notes: 0, highlights: 0, ai_notes: 0, ...o }) as DeckPaper
const PAPERS = [paper({}), paper({ paper_id: 'p2', key: 'vaswani2017', title: 'Attention is all you need', first_author: 'Vaswani', year: 2017 })]

function setup(doc: string, onCite = vi.fn()) {
  const { container } = render(<LatexEditor value={doc} onChange={() => {}} errors={[]} onSave={() => {}} citeOptions={PAPERS} onCite={onCite} />)
  const view = EditorView.findFromDOM(container.querySelector<HTMLElement>('.cm-editor')!)!
  return { view, onCite, container }
}
const open = async (view: EditorView, at: number) => {
  view.dispatch({ selection: { anchor: at } })
  startCompletion(view)
  await vi.waitFor(() => expect(completionStatus(view.state)).toBe('active'))
  return currentCompletions(view.state).map((c) => c.label)
}

test('opens inside \\citep{ and after a comma, with key, author, year and title', async () => {
  const a = setup('\\citep{')
  const labels = await open(a.view, 7)
  expect(labels).toContain('lewis2020 — Lewis 2020: Retrieval-augmented generation')
  const b = setup('\\citep{lewis2020,')
  expect((await open(b.view, 17)).length).toBe(2)
})

test('does not open outside a cite argument', async () => {
  for (const [doc, at] of [['hello', 5], ['\\citep{a} x', 11], ['\\section{', 9]] as const) {
    const { view } = setup(doc)
    view.dispatch({ selection: { anchor: at } })
    startCompletion(view)
    await new Promise((r) => setTimeout(r, 50))
    expect(completionStatus(view.state)).toBeNull()
  }
})

test('accepting inserts the key and pins the paper once', async () => {
  const { view, onCite } = setup('\\citep{vas')
  await open(view, 10)
  await new Promise((r) => setTimeout(r, 120)) // the list ignores an accept right as it opens
  acceptCompletion(view)
  expect(view.state.doc.toString()).toBe('\\citep{vaswani2017')
  expect(onCite).toHaveBeenCalledTimes(1)
  expect(onCite).toHaveBeenCalledWith('p2')
})

test('a drop carrying a paper pins it once and does not stop the editor taking the text', () => {
  const { container, onCite, view } = setup('x')
  view.posAtCoords = () => 1 // jsdom has no layout: say the drop is at the end
  const ev = new Event('drop', { bubbles: true, cancelable: true }) as Event & { dataTransfer: unknown }
  ev.dataTransfer = { types: ['text/plain', 'application/x-paperlab-paper'], getData: (t: string) => (t === 'application/x-paperlab-paper' ? 'p1' : '\\citep{lewis2020}') }
  container.querySelector('.cm-content')!.dispatchEvent(ev)
  expect(onCite).toHaveBeenCalledTimes(1)
  expect(onCite).toHaveBeenCalledWith('p1')
  expect(view.state.doc.toString()).toBe('x\\citep{lewis2020}')
})

test('a plain-text drop does not pin', () => {
  const { container, onCite, view } = setup('x')
  view.posAtCoords = () => 1
  const ev = new Event('drop', { bubbles: true, cancelable: true }) as Event & { dataTransfer: unknown }
  ev.dataTransfer = { types: ['text/plain'], getData: () => 'hi' }
  container.querySelector('.cm-content')!.dispatchEvent(ev)
  expect(onCite).not.toHaveBeenCalled()
})
