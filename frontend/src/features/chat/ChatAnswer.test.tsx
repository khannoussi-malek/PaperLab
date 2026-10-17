// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ChatSource } from '@/api/client'
import { ChatAnswer } from './ChatAnswer'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const source = (n: number): ChatSource =>
  ({ label: `C${n}`, chunk_id: `chunk-${n}`, paper_id: 'p1', page: n, section: null, bbox: null }) as unknown as ChatSource
const sources = Array.from({ length: 53 }, (_, i) => source(i + 1))
const segments = [
  { kind: 'text' as const, text: 'Both agree ' },
  { kind: 'cite' as const, label: 'C1' },
  { kind: 'cite' as const, label: 'C2' },
]
const base = {
  question: 'q?', wholePaper: false, sources, notes: [], notesUsed: null, notesTotal: null, segments,
  footer: null, onCite: () => {},
}
const chips = () => within(screen.getByRole('list', { name: 'Sources' })).queryAllByRole('button')

describe('ChatAnswer sources', () => {
  it('only cited sources show until Show all is pressed', () => {
    render(<ChatAnswer {...base} />)
    expect(chips().map((b) => b.textContent)).toEqual(['C1', 'C2'])
    fireEvent.click(screen.getByRole('button', { name: 'Show all 53 sources' }))
    expect(chips()).toHaveLength(53)
    expect(screen.queryByRole('button', { name: /Show all/ })).toBeNull()
  })

  it('shows only what is cited so far while streaming, without a Show all', () => {
    render(<ChatAnswer {...base} pending />)
    expect(chips()).toHaveLength(2)
  })

  it('whole-paper answers are unchanged', () => {
    render(<ChatAnswer {...base} wholePaper sources={sources.slice(0, 5)} segments={[{ kind: 'text', text: 'x' }]} />)
    expect(screen.getByText('Whole paper · 5 chunks')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show all/ })).toBeNull()
  })

  it('explains "Using X of Y notes" with a Term beside the text', () => {
    render(<ChatAnswer {...base} notesUsed={3} notesTotal={9} />)
    expect(screen.getByText(/Using 3 of 9/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /notes/ }).parentElement?.closest('button')).toBeNull()
  })

  it('counts only real sources: a replaced (null) one is not in "Show all N"', () => {
    const four = [source(1), null, source(2), source(3), source(4)]
    render(<ChatAnswer {...base} sources={four} />)
    expect(chips()).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Show all 4 sources' }))
    expect(chips()).toHaveLength(4)
    expect(screen.queryByRole('button', { name: /Show all/ })).toBeNull()
  })

  it('has no Show all when everything is already cited', () => {
    render(<ChatAnswer {...base} sources={[source(1), source(2)]} />)
    expect(chips()).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /Show all/ })).toBeNull()
  })

  it('an answer citing nothing shows no chips and a Show all button', () => {
    render(<ChatAnswer {...base} segments={[{ kind: 'text', text: 'No citations.' }]} />)
    expect(chips().filter((b) => /^C\d+$/.test(b.textContent ?? ''))).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Show all 53 sources' })).toBeInTheDocument()
  })
})
