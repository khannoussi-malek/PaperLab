import type { Paper } from '@/api/client'

const ACRONYM = /\(([A-Z][A-Z0-9&-]{1,11}(?:\s?'?\d{2,4})?)\)\s*$/
const BOILERPLATE = /^(?:Proceedings of the (?:\d+(?:st|nd|rd|th) )?(?:Annual )?|\d{4} )/i

/** "Symposium on Theory of Computing (STOC)" -> "STOC"; otherwise the full name minus "Proceedings of the 57th" and a
 * leading year (the chip shows the year itself). CSS truncates what is still too long. */
export function venueShort(venue: string): string {
  const acronym = ACRONYM.exec(venue)?.[1]
  if (acronym) return acronym
  const name = venue.replace(BOILERPLATE, '').replace(BOILERPLATE, '').trim()
  return name || venue
}

/** The chip's visible text: "Published: STOC 2025". Either part may be missing. */
export const publishedChipText = (venue: string | null | undefined, year: number | null | undefined): string => {
  const rest = [venue ? venueShort(venue) : null, year].filter(Boolean).join(' ')
  return rest ? `Published: ${rest}` : 'Published'
}

/** A preprint copy whose published version is known: one "Published" chip replaces "Preprint" and "Peer-reviewed". */
export const isPublishedCopy = (paper: Pick<Paper, 'source_type' | 'published_venue' | 'published_doi'>): boolean =>
  paper.source_type === 'preprint' && Boolean(paper.published_venue || paper.published_doi)
