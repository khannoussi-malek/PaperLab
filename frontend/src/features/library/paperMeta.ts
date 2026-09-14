import type { Paper } from '@/api/client'

const SHORT_AUTHOR_COUNT = 2

export function shortAuthors(authors: string[]): string {
  const shown = authors.slice(0, SHORT_AUTHOR_COUNT).join(', ')
  return authors.length > SHORT_AUTHOR_COUNT ? `${shown} et al.` : shown
}

export const pageCountLabel = (count: number | null): string =>
  count ? `${count} ${count === 1 ? 'page' : 'pages'}` : ''

/** "Ada, Alan et al. · 2017 · NeurIPS", leaving out whatever is missing. */
export const byline = (paper: Pick<Paper, 'authors' | 'year' | 'venue'>): string =>
  [shortAuthors(paper.authors), paper.year, paper.venue].filter(Boolean).join(' · ')
