import { describe, expect, it } from 'vitest'
import { ALL_NOTES, emptyNotesText, filterOptions, filterValue, routeFilter } from './notesPage'

describe('the Notes page filter', () => {
  it('offers All notes, No paper, then the library’s papers by title, then id', () => {
    const papers = [
      { id: 'p2', title: 'BERT' },
      { id: 'p1', title: 'Attention' },
      { id: 'p0', title: 'BERT' },
    ]
    expect(filterOptions(papers)).toEqual([
      { value: 'all', label: 'All notes' },
      { value: 'none', label: 'No paper' },
      { value: 'p1', label: 'Attention' },
      { value: 'p0', label: 'BERT' },
      { value: 'p2', label: 'BERT' },
    ])
  })

  it('maps the route’s filter to the select and back', () => {
    expect([filterValue(null), filterValue('none'), filterValue('p1')]).toEqual([ALL_NOTES, 'none', 'p1'])
    expect([routeFilter(ALL_NOTES), routeFilter('none'), routeFilter('p1')]).toEqual([null, 'none', 'p1'])
  })

  it('says, for each filter, that it has no notes', () => {
    expect(emptyNotesText(null)).toBe('No notes yet. Highlight a passage in a paper, or save a note chat suggests.')
    expect(emptyNotesText('none')).toBe('No notes without a paper. A note you take off its last paper shows here.')
    expect(emptyNotesText('p1')).toBe('No notes on this paper yet.')
  })
})
