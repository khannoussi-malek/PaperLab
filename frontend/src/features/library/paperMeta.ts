import type { Paper } from '@/api/client'

const SHORT_AUTHOR_COUNT = 2
const LABEL_CHARS = 24

export function shortAuthors(authors: string[]): string {
  const shown = authors.slice(0, SHORT_AUTHOR_COUNT).join(', ')
  return authors.length > SHORT_AUTHOR_COUNT ? `${shown} et al.` : shown
}

export const pageCountLabel = (count: number | null): string =>
  count ? `${count} ${count === 1 ? 'page' : 'pages'}` : ''

/** "Ada, Alan et al. · 2017 · NeurIPS", leaving out whatever is missing. */
export const byline = (paper: Pick<Paper, 'authors' | 'year' | 'venue'>): string =>
  [shortAuthors(paper.authors), paper.year, paper.venue].filter(Boolean).join(' · ')

/** Lower-case words with accents and punctuation dropped, so "muller" finds "Müller" and "pre-training" is two words. */
const wordsOf = (text: string): string[] =>
  text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean)

/**
 * True when every word of `query` starts a word of the title, an author, the year or the venue: "train" finds
 * "training", but "ai" doesn't. A blank query matches all.
 */
export function matchesPaper(paper: Pick<Paper, 'title' | 'authors' | 'year' | 'venue'>, query: string): boolean {
  const words = wordsOf([paper.title, ...paper.authors, paper.year, paper.venue].join(' '))
  return wordsOf(query).every((part) => words.some((word) => word.startsWith(part)))
}

/**
 * A paper's short name where an answer cites several papers, by the backend's source_label rule, so it matches the
 * prompt the model saw: "Karpukhin 2020", "Karpukhin" without a year, or the title cut to 24 characters when no author
 * name is known.
 */
export function paperLabel(paper: Pick<Paper, 'title' | 'authors' | 'year'>): string {
  const family = paper.authors.find((name) => name.trim())?.trim().split(/\s+/).at(-1)
  if (family) return paper.year ? `${family} ${paper.year}` : family
  return paper.title.length > LABEL_CHARS ? `${paper.title.slice(0, LABEL_CHARS - 1)}…` : paper.title
}
