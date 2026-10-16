import type { Paper } from '@/api/client'

const VENUE_MAX = 40

/** "Symposium on Theory of Computing (STOC)" -> "STOC"; any other venue is cut at 40 characters with "…". */
export function venueShort(venue: string): string {
  const abbreviation = /\(([^()]+)\)\s*$/.exec(venue)?.[1]
  if (abbreviation) return abbreviation
  return venue.length > VENUE_MAX ? `${venue.slice(0, VENUE_MAX)}…` : venue
}

/** "Published: STOC 2025"; either part may be missing. */
export const publishedChipText = (venue: string | null | undefined, year: number | null | undefined): string => {
  const rest = [venue ? venueShort(venue) : null, year].filter(Boolean).join(' ')
  return rest ? `Published: ${rest}` : 'Published'
}

/** A preprint copy whose published version is known: one "Published" chip replaces "Preprint" and "Peer-reviewed". */
export const isPublishedCopy = (paper: Pick<Paper, 'source_type' | 'published_venue' | 'published_doi'>): boolean =>
  paper.source_type === 'preprint' && Boolean(paper.published_venue || paper.published_doi)
