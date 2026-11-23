// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ReadingList, type ReadingRow } from './ReadingList'

const rows: ReadingRow[] = [
  { paper_id: 'p1', label: 'Smith 2021', status: 'found', answer: 'Pill counts.', low_confidence: false,
    cited: [{ chunk_id: 'c1', page: 4, section: 'Methods', text: 'Adherence was measured by pill count.' }] },
  { paper_id: 'p2', label: 'Lee 2020', status: 'absent', answer: 'Only dosing.', low_confidence: false, cited: [] },
  { paper_id: 'p3', label: 'Bare', status: 'no_text', answer: '', low_confidence: false, cited: [] },
  { paper_id: 'p4', label: 'Wu 2019', status: 'model_error', answer: '', low_confidence: false, cited: [] },
]

describe('ReadingList', () => {
  it('shows each paper with its status while reading, and how far it got', () => {
    render(<ReadingList readings={rows.slice(0, 2)} total={4} live />)
    expect(screen.getByText('Reading 2 of 4 papers')).toBeInTheDocument()
    expect(screen.getByText('Smith 2021')).toBeInTheDocument()
    expect(screen.getByText('found')).toBeInTheDocument()
    expect(screen.getByText("doesn't cover this")).toBeInTheDocument()
  })

  it('collapses to a summary under a saved answer and opens to each record', () => {
    render(<ReadingList readings={rows} />)
    const summary = screen.getByText("Read 4 papers: 1 found, 1 don't cover this, 2 couldn't be read")
    expect(screen.queryByText('Pill counts.')).not.toBeVisible()
    fireEvent.click(summary)
    expect(screen.getByText('Pill counts.')).toBeVisible()
    expect(screen.getByText('Adherence was measured by pill count.')).toBeVisible()
    expect(screen.getByText('no text')).toBeInTheDocument()
    expect(screen.getByText("couldn't read")).toBeInTheDocument()
  })

  it('marks a found record with no passage to show for it', () => {
    render(<ReadingList readings={[{ ...rows[0], cited: [], low_confidence: true }]} live total={1} />)
    expect(screen.getByText('found, no passage cited')).toBeInTheDocument()
  })
})
