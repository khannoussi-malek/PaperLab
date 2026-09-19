import { describe, expect, it } from 'vitest'
import type { Reference, References } from '@/api/client'
import { joinLines, type Entry } from './citationEntry'
import { cardView, doiIn, matchEntry, titleScore, UNMATCHED_LINES } from './citationMatch'

const row = (fields: Partial<Reference>): Reference => ({
  id: 'r1',
  title: 'Untitled',
  authors: ['Ada Fixture'],
  year: 2026,
  venue: null,
  doi: null,
  arxiv_id: null,
  openalex_id: null,
  s2_id: null,
  cited_by_count: null,
  has_pdf: false,
  cocitation: 1,
  paper_id: null,
  position: 0,
  ...fields,
})

/** An entry as the reader reads it: printed lines, joined as `citationEntry` joins them. */
const entryOf = (...lines: string[]): Entry => ({ page: 2, lines, text: joinLines(lines), rects: [] })

describe('matching by DOI', () => {
  it('finds a DOI broken across lines at its hyphen, in any case', () => {
    const free = row({ id: 'free', doi: '10.5555/PaperLab-E2E-Free' })
    const entry = entryOf('[1] Ada Fixture. 2026. Journal. doi:10.5555/paperlab-e2e-', 'free')
    expect(matchEntry(entry, [row({ doi: '10.5555/paperlab-e2e-landing' }), free])).toBe(free)
  })

  it('prefers the longest stored DOI the entry holds, so a prefix never wins', () => {
    const [prefix, full] = [row({ id: 'a', doi: '10.1145/3377811' }), row({ id: 'b', doi: '10.1145/3377811.3380330' })]
    expect(matchEntry(entryOf('[2] In ICSE. doi:10.1145/3377811.3380330'), [prefix, full])).toBe(full)
  })

  it('beats a title that also matches', () => {
    const [byTitle, byDoi] = [
      row({ id: 't', title: 'Attention Is All You Need' }),
      row({ id: 'd', title: 'Another paper entirely', doi: '10.5555/x-1' }),
    ]
    expect(matchEntry(entryOf('[3] Attention is all you need. doi:10.5555/x-1'), [byTitle, byDoi])).toBe(byDoi)
  })
})

describe('matching by arXiv id', () => {
  const lora = row({ id: 'lora', title: 'LoRA', arxiv_id: '2106.09685' })

  it.each([
    'arXiv:2106.09685',
    'https://arxiv.org/abs/2106.09685',
    'arxiv.org/pdf/2106.09685v2',
    'doi:10.48550/arXiv.2106.09685',
    'CoRR abs/2106.09685',
    'arXiv:2106.09685v3 [cs.CL]',
  ])('finds %s', (printed) => {
    expect(matchEntry(entryOf(`[4] Hu et al. 2021. ${printed}`), [lora])).toBe(lora)
  })

  it('never matches a bare number, or a longer id', () => {
    expect(matchEntry(entryOf('[4] Page 2106.09685 of something'), [lora])).toBeNull()
    expect(matchEntry(entryOf('[4] arXiv:2106.096851'), [lora])).toBeNull()
  })
})

describe('matching by title', () => {
  const attention = row({ id: 'attention', title: 'Attention Is All You Need' })

  it('scores an exact title 1, a one-character glitch at least 0.9, and another title below 0.9', () => {
    const cited = '[5] Ashish Vaswani and others. 2017. Attention is all you need. In NeurIPS.'
    expect(titleScore(attention.title, cited)).toBe(1)
    expect(titleScore(attention.title, '[5] Vaswani. 2017. Attention is al you need. In NeurIPS.')).toBeGreaterThanOrEqual(0.9)
    expect(titleScore(attention.title, '[5] Someone. 2020. Attention is not what you need.')).toBeLessThan(0.9)
    expect(matchEntry(entryOf(cited), [attention])).toBe(attention)
    expect(matchEntry(entryOf('[5] Someone. 2020. Attention is not what you need.'), [attention])).toBeNull()
  })

  it('ignores a stored title under 16 letters and digits, even when it appears', () => {
    expect(matchEntry(entryOf('[6] Devlin et al. 2019. BERT. In NAACL.'), [row({ title: 'BERT' })])).toBeNull()
  })

  it('takes the longest when two stored titles both appear in full', () => {
    const [short, long] = [
      row({ id: 'queue', title: 'The SPACE of developer productivity', position: 0 }),
      row({ id: 'cacm', title: "The SPACE of Developer Productivity: There's more to it than you think", position: 1 }),
    ]
    const entry = entryOf("[7] Forsgren et al. 2021. The SPACE of Developer Productivity: There's more to it than you think.")
    expect(matchEntry(entry, [short, long])).toBe(long)
  })

  it('breaks a tie of equal score and title length by the lower position', () => {
    const [later, earlier] = [
      row({ id: 'later', title: 'A Paper About Distributed Systems', position: 5 }),
      row({ id: 'earlier', title: 'A Paper About Distributed Systems', position: 2 }),
    ]
    const entry = entryOf('[8] Someone. 2020. A Paper About Distributed Systems.')
    expect(matchEntry(entry, [later, earlier])).toBe(earlier)
  })
})

describe('doiIn', () => {
  it('finds the first DOI, lower-cased, without trailing punctuation', () => {
    expect(doiIn('[3] In ICSE (https://doi.org/10.1145/3377811.3380330).')).toBe('10.1145/3377811.3380330')
    expect(doiIn('[1] Journal. DOI: 10.5555/PaperLab-E2E-free; more')).toBe('10.5555/paperlab-e2e-free')
    expect(doiIn('[3] Some Author. 2019. A paper this library has never stored.')).toBeNull()
  })

  it('also trims a trailing ] or >, from an angle-bracketed link or a bracketed entry', () => {
    expect(doiIn('Available at <https://doi.org/10.1145/3377811>.')).toBe('10.1145/3377811')
    expect(doiIn('[10.1000/xyz123]')).toBe('10.1000/xyz123')
  })
})

describe('what the card shows', () => {
  const entry = entryOf('[1] Ada Fixture. 2026. doi:10.5555/paperlab-e2e-', 'free')
  const listing = (state: References['state'], rows: Reference[] = []) => ({
    data: { state, error: null, direction: 'cites' as const, summary: { cited_by_3plus: 0, with_pdf: 0 }, rows },
    isError: false,
  })
  const free = (fields: Partial<Reference>) => row({ doi: '10.5555/paperlab-e2e-free', ...fields })

  it('says unreadable for an entry over the caps, whatever the listing', () => {
    expect(cardView({ entry: null }, { data: undefined, isError: false })).toEqual({ kind: 'unreadable' })
  })

  it('waits for the listing, then shows a matched reference by where it stands', () => {
    expect(cardView({ entry }, { data: undefined, isError: false })).toEqual({ kind: 'loading' })
    expect(cardView({ entry }, listing('ready', [free({ paper_id: 'p1', has_pdf: true })])).kind).toBe('in-library')
    expect(cardView({ entry }, listing('ready', [free({ has_pdf: true })])).kind).toBe('free-pdf')
    expect(cardView({ entry }, listing('ready', [free({})])).kind).toBe('details')
  })

  it('shows the entry as printed when nothing matches, with a line for each state of the references', () => {
    const unmatched = (references: Parameters<typeof cardView>[1]) => {
      const view = cardView({ entry }, references)
      if (view.kind !== 'unmatched') throw new Error(`expected unmatched, got ${view.kind}`)
      return { line: UNMATCHED_LINES[view.state], open: view.openReferences, text: view.text, doi: view.doi }
    }
    expect(unmatched(listing('none'))).toEqual({
      line: "This paper's references haven't been looked up.",
      open: true,
      text: '[1] Ada Fixture. 2026. doi:10.5555/paperlab-e2e-free',
      doi: '10.5555/paperlab-e2e-free',
    })
    expect(unmatched(listing('failed'))).toMatchObject({ line: "Looking up this paper's references failed.", open: true })
    expect(unmatched(listing('fetching'))).toMatchObject({ line: "Looking up this paper's references…", open: false })
    expect(unmatched(listing('ready', [row({ title: 'Nothing like it at all, here' })]))).toMatchObject({ line: null, open: false })
    expect(unmatched({ data: undefined, isError: true })).toMatchObject({ line: "Couldn't check your library for it.", open: false })
  })
})
