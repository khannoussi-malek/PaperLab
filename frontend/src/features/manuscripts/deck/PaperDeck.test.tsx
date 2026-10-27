// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PaperDeck } from './PaperDeck'
import type { DeckPaper } from './deckModel'

const mk = (i: number, over: Partial<DeckPaper> = {}): DeckPaper => ({
  paper_id: `p${i}`, key: `k${i}`, pinned: false, title: `${String.fromCharCode(97 + (i % 26))} paper ${i}`,
  first_author: 'Lewis', year: 2020, has_pdf: true, notes: 0, highlights: 0, ai_notes: 0, ...over,
})

function setup(papers: DeckPaper[], current = 1, extra: Record<string, unknown> = {}) {
  const onCurrent = vi.fn(), onOpen = vi.fn(), onFilter = vi.fn()
  render(<PaperDeck papers={papers} current={current} onCurrent={onCurrent} onOpen={onOpen} filter="" onFilter={onFilter} label="Papers" {...extra} />)
  return { onCurrent, onOpen, onFilter, deck: screen.getByRole('group', { name: 'Papers' }) }
}

afterEach(() => vi.unstubAllGlobals())

describe('PaperDeck', () => {
  const five = [0, 1, 2, 3, 4].map((i) => mk(i))

  it('moves with arrows, Home, End and a letter', () => {
    const { onCurrent, deck } = setup(five)
    fireEvent.keyDown(deck, { key: 'ArrowRight' }); expect(onCurrent).toHaveBeenLastCalledWith(2)
    fireEvent.keyDown(deck, { key: 'ArrowLeft' }); expect(onCurrent).toHaveBeenLastCalledWith(0)
    fireEvent.keyDown(deck, { key: 'End' }); expect(onCurrent).toHaveBeenLastCalledWith(4)
    fireEvent.keyDown(deck, { key: 'Home' }); expect(onCurrent).toHaveBeenLastCalledWith(0)
    fireEvent.keyDown(deck, { key: 'e' }); expect(onCurrent).toHaveBeenLastCalledWith(4)
  })

  it('opens with Enter and a click on the current card, flips on another', () => {
    const { onCurrent, onOpen, deck } = setup(five)
    fireEvent.keyDown(deck, { key: 'Enter' }); expect(onOpen).toHaveBeenLastCalledWith(1)
    fireEvent.click(deck.querySelector('[data-deck-card="p1"]')!); expect(onOpen).toHaveBeenCalledTimes(2)
    fireEvent.click(deck.querySelector('[data-deck-card="p3"]')!); expect(onCurrent).toHaveBeenLastCalledWith(3)
  })

  it('wheel flips', () => {
    const { onCurrent, deck } = setup(five)
    fireEvent.wheel(deck, { deltaY: 40 }); expect(onCurrent).toHaveBeenLastCalledWith(2)
  })

  it('keeps at most 7 cards in the DOM for 500 papers', () => {
    const { deck } = setup(Array.from({ length: 500 }, (_, i) => mk(i)), 250)
    expect(deck.querySelectorAll('[data-deck-card]').length).toBe(7)
  })

  it('announces the current paper', () => {
    setup([mk(0), mk(1, { notes: 2, highlights: 1 }), mk(2), mk(3), mk(4)])
    expect(screen.getByRole('status').textContent).toBe('Lewis 2020, 2 notes, 1 highlight, paper 2 of 5')
  })

  it('renders a paper with no year or authors, and badges', () => {
    setup([mk(0, { year: null, first_author: null, title: 'Bare', notes: 1, highlights: 2, ai_notes: 3 })], 0, { cited: new Set(['k0']) })
    expect(screen.getAllByText('Bare').length).toBeGreaterThan(0)
    expect(screen.getByText('cited')).toBeTruthy()
    expect(screen.getByText('1 N')).toBeTruthy()
    expect(screen.getByText('2 H')).toBeTruthy()
    expect(screen.getByText('3 A')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toBe('Bare, 1 note, 2 highlights, 3 AI notes, paper 1 of 1')
  })

  it('shows the two empty states', () => {
    const { rerender } = render(<PaperDeck papers={[]} current={0} onCurrent={vi.fn()} onOpen={vi.fn()} filter="" onFilter={vi.fn()} label="Papers" />)
    expect(screen.getByText('No papers in this workspace yet')).toBeTruthy()
    rerender(<PaperDeck papers={[]} current={0} onCurrent={vi.fn()} onOpen={vi.fn()} filter="zzz" onFilter={vi.fn()} label="Papers" />)
    expect(screen.getByText('No paper matches')).toBeTruthy()
  })

  it('moves with the filter box and reports typing', () => {
    const { onFilter } = setup(five)
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search papers' }), { target: { value: 'ab' } })
    expect(onFilter).toHaveBeenCalledWith('ab')
  })

  it('uses a transition normally and none with reduced motion', () => {
    const { deck } = setup(five)
    expect((deck.querySelector('[data-deck-card="p1"]') as HTMLElement).style.transition).toContain('500ms')
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: true, media: q, addEventListener() {}, removeEventListener() {} }))
    document.body.innerHTML = ''
    const again = setup(five)
    expect((again.deck.querySelector('[data-deck-card="p1"]') as HTMLElement).style.transition).toBe('none')
  })
})
