import { getDocument } from 'pdfjs-dist/legacy/build/pdf.mjs'
import { describe, expect, it } from 'vitest'
import type { Reference } from '@/api/client'
import { matchEntry, titleScore } from './citationMatch'
import { citationsByPage, readCitations, type Citation } from './citations'

// The committed E2E fixture (e2e/fixtures/make_citation_paper.py) through PDF.js's legacy build in Node: the real
// pipeline, with PDF.js's own item splits and coordinate flips (D148). A path, not node:fs: tsc keeps vite/client.
const FIXTURE = decodeURIComponent(new URL('../../../e2e/fixtures/citation-paper.pdf', import.meta.url).pathname)

async function readFixture(): Promise<Citation[]> {
  const task = getDocument({ url: FIXTURE, verbosity: 0 }) // 0: errors only, not PDF.js's standard-font warnings
  try {
    return await readCitations(await task.promise)
  } finally {
    await task.destroy()
  }
}

const loaded = readFixture()
const cited = async (label: number) => (await loaded).find((citation) => citation.label === label)!

/** The three references the fake discovery provider gives every library paper (backend/app/providers/discovery_fake.py). */
const fake = (title: string, slug: string, position: number): Reference => ({
  id: slug,
  title,
  authors: ['Ada Fixture'],
  year: 2026,
  venue: 'Journal of Fixtures',
  doi: `10.5555/paperlab-e2e-${slug}`,
  arxiv_id: null,
  openalex_id: null,
  s2_id: null,
  cited_by_count: 3,
  has_pdf: slug !== 'closed',
  cocitation: 1,
  paper_id: null,
  position,
})
const [FREE, LANDING, CLOSED] = [
  fake('PaperLab Find Papers Fixture', 'free', 0),
  fake('PaperLab Landing Page Fixture', 'landing', 1),
  fake('PaperLab Closed Access Fixture', 'closed', 2),
]

describe('the citation fixture, read the way the reader reads it', () => {
  it('finds exactly the four linked citations on page 1, and not Figure 1 or 2 pages', async () => {
    const citations = await loaded
    expect(citations.map((citation) => [citation.page, citation.label])).toEqual([
      [1, 1],
      [1, 2],
      [1, 3],
      [1, 4],
    ])
    expect([...citationsByPage(citations).keys()]).toEqual([1])
    // The link over [1]'s digits, flipped to the reader's top-left points.
    expect(citations[0].rect.map(Math.round)).toEqual([176, 108, 182, 123])
  })

  it('reads [1] whole, its DOI joined across the line break with the hyphen kept', async () => {
    expect((await cited(1)).entry?.text).toBe(
      '[1] Ada Fixture. 2026. PaperLab Fixture for Finding Papers. Journal of Fixtures. doi:10.5555/paperlab-e2e-free',
    )
  })

  it('reads [2] across the columns, without the running header, and jumps to its first line', async () => {
    const two = await cited(2)
    expect(two.entry?.text).toMatch(/PaperLab Closed Access Fixture\. Journal of Fixtures\.$/)
    expect(two.entry?.text).not.toContain('Fixture Proceedings 2026')
    expect(two.jump.page).toBe(2)
    expect(two.jump.rects[0].map(Math.round)).toEqual([54, 720, 261, 731])
  })

  it('reads [3] exactly', async () => {
    expect((await cited(3)).entry?.text).toBe('[3] Some Author. 2019. A paper this library has never stored. Unknown Venue.')
  })

  it('matches FREE by DOI, CLOSED by title, nothing for [3], and LANDING by DOI', async () => {
    const rows = [FREE, LANDING, CLOSED]
    const one = (await cited(1)).entry!
    expect(titleScore(FREE.title, one.text)).toBeLessThan(0.9) // only its DOI can match it
    expect(matchEntry(one, rows)).toBe(FREE)
    expect(matchEntry((await cited(2)).entry!, rows)).toBe(CLOSED)
    expect(matchEntry((await cited(3)).entry!, rows)).toBeNull()
    expect(matchEntry((await cited(4)).entry!, rows)).toBe(LANDING)
  })
})
