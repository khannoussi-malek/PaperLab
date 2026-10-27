// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PaperBook } from './PaperBook'
import type { BookItem, DeckPaper } from './deckModel'
import * as pageTurn from './pageTurn'

const paper: DeckPaper = { paper_id: 'p1', key: 'lewis20', pinned: false, title: 'Retrieval paper', first_author: 'Lewis', year: 2020, has_pdf: true, notes: 1, highlights: 2, ai_notes: 1 }
const items: BookItem[] = [
  { id: 'a:h0', kind: 'highlight', page: 2, text: 'first quote', noteId: 'a' },
  { id: 'b:note', kind: 'note', page: null, text: 'my note', noteId: 'b' },
  { id: 'c:ai', kind: 'ai', page: 4, text: 'model said', noteId: 'c' },
]

const finishes: ReturnType<typeof vi.fn>[] = []
let turnSpy: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  finishes.length = 0
  turnSpy = vi.spyOn(pageTurn, 'turnLeaf').mockImplementation(() => {
    const finish = vi.fn()
    finishes.push(finish)
    return { finish }
  })
})

function Harness({ list = items, start = 0, ...fns }: { list?: BookItem[]; start?: number } & Record<string, unknown>) {
  const [sel, setSel] = useState(start)
  return <PaperBook paper={paper} items={list} selected={sel} onSelect={setSel} onInsert={() => {}} onOpenReader={() => {}} onClose={() => {}} {...fns} />
}
const book = () => screen.getByRole('group', { name: 'Retrieval paper' })

describe('PaperBook', () => {
  it('turns the cover on open, then forward and back with the right direction', () => {
    render(<Harness />)
    expect(turnSpy.mock.calls[0][1]).toBe('fwd')
    fireEvent.keyDown(book(), { key: 'ArrowDown' })
    expect(turnSpy.mock.calls[1][1]).toBe('fwd')
    fireEvent.keyDown(book(), { key: 'ArrowUp' })
    expect(turnSpy.mock.calls[2][1]).toBe('bwd')
  })

  it('finishes the running turn before starting the next', () => {
    render(<Harness />)
    fireEvent.keyDown(book(), { key: 'ArrowDown' })
    const first = finishes[1]
    fireEvent.keyDown(book(), { key: 'ArrowDown' })
    expect(first).toHaveBeenCalled()
    expect(turnSpy).toHaveBeenCalledTimes(3)
  })

  it('does not run past the ends', () => {
    render(<Harness start={2} />)
    const n = turnSpy.mock.calls.length
    fireEvent.keyDown(book(), { key: 'ArrowDown' })
    expect(turnSpy).toHaveBeenCalledTimes(n)
  })

  it('i, o and Escape call back with the selected item', () => {
    const onInsert = vi.fn(), onOpenReader = vi.fn(), onClose = vi.fn()
    render(<Harness onInsert={onInsert} onOpenReader={onOpenReader} onClose={onClose} />)
    fireEvent.keyDown(book(), { key: 'i' }); expect(onInsert).toHaveBeenCalledWith(items[0])
    fireEvent.keyDown(book(), { key: 'o' }); expect(onOpenReader).toHaveBeenCalledWith(items[0])
    fireEvent.keyDown(book(), { key: 'Escape' }); expect(onClose).toHaveBeenCalled()
  })

  it('tabs carry data-book-tab, a letter and a page', () => {
    const { container } = render(<Harness />)
    const tab = container.querySelector('[data-book-tab="c:ai"]')!
    expect(tab.textContent).toBe('A4')
    fireEvent.click(tab)
    expect(screen.getByText('Insert as comment')).toBeTruthy()
    expect(container.querySelector('[data-book-tab="b:note"]')!.textContent).toBe('N')
  })

  it('names the insert button by kind and always offers the paper citation', () => {
    const onInsert = vi.fn()
    render(<Harness onInsert={onInsert} />)
    fireEvent.click(screen.getByText('Insert quote + \\citep'))
    expect(onInsert).toHaveBeenLastCalledWith(items[0])
    fireEvent.click(screen.getByText('Insert \\citep{lewis20}'))
    expect(onInsert).toHaveBeenLastCalledWith(null)
  })

  it('shows a single no-notes page and still inserts the paper', () => {
    const onInsert = vi.fn()
    render(<Harness list={[]} onInsert={onInsert} />)
    expect(screen.getAllByText('No notes on this paper yet').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByText('Insert \\citep{lewis20}'))
    expect(onInsert).toHaveBeenCalledWith(null)
    fireEvent.keyDown(book(), { key: 'ArrowDown' })
  })

  it('starts from the clamped selection, so an out-of-range one turns nothing but the cover', () => {
    render(<Harness start={9} />)
    expect(turnSpy).toHaveBeenCalledTimes(1)
  })

  it('a turn that lands after the book is gone sets nothing', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { unmount } = render(<Harness />)
    const land = turnSpy.mock.calls[0][4]?.land
    unmount()
    land?.()
    expect(errors).not.toHaveBeenCalled()
    errors.mockRestore()
  })

  it('an AI note is not draggable (a drop would land mid-line); your own notes are', () => {
    render(<Harness />)
    const li = (text: string) => screen.getByText(text).closest('li')!
    expect(li('model said')).toHaveAttribute('draggable', 'false')
    expect(li('my note')).toHaveAttribute('draggable', 'true')
    const setData = vi.fn()
    fireEvent.dragStart(li('model said'), { dataTransfer: { setData, types: [] } })
    expect(setData).not.toHaveBeenCalled()
  })

  it("shows the verdict under a selected passage, marked AI, with its quote's page", () => {
    const ev: BookItem[] = [{ id: 'k1:e', kind: 'evidence', page: 3, text: 'a passage', noteId: 'k1', chunkId: 'k1' }]
    const verdict = { label: 'Supports', text: 'Supports', ai: true, quote: 'Cats do purr', reason: 'It says so', page: 7 }
    render(<Harness list={ev} verdict={verdict} />)
    expect(screen.getByText('AI')).toBeTruthy()
    expect(screen.getByText(/Cats do purr/).closest('p')!.textContent).toBe('“Cats do purr” p. 7')
  })

  it('announces the item', () => {
    render(<Harness />)
    expect(screen.getByRole('status').textContent).toBe('Your highlight, page 2: first quote. 1 of 3.')
  })
})
