import type { Paper } from '@/api/client'

const SHORT_AUTHOR_COUNT = 2

// `authors` is untyped JSON until enrichment (roadmap M6.5) fixes its shape, so read names defensively.
function authorName(author: unknown): string {
  if (typeof author === 'string') return author.trim()
  if (author && typeof author === 'object') {
    const { name, display_name } = author as Record<string, unknown>
    const value = typeof name === 'string' ? name : display_name
    return typeof value === 'string' ? value.trim() : ''
  }
  return ''
}

export const authorNames = (authors: unknown[]): string[] => authors.map(authorName).filter(Boolean)

export function shortAuthors(authors: unknown[]): string {
  const names = authorNames(authors)
  const shown = names.slice(0, SHORT_AUTHOR_COUNT).join(', ')
  return names.length > SHORT_AUTHOR_COUNT ? `${shown} et al.` : shown
}

export const pageCountLabel = (count: number | null): string =>
  count ? `${count} ${count === 1 ? 'page' : 'pages'}` : ''

/** "Ada, Alan et al. · 2017 · NeurIPS", leaving out whatever is missing. */
export const byline = (paper: Pick<Paper, 'authors' | 'year' | 'venue'>): string =>
  [shortAuthors(paper.authors), paper.year, paper.venue].filter(Boolean).join(' · ')
