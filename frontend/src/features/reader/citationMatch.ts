import type { UseQueryResult } from '@tanstack/react-query'
import type { Reference, References } from '@/api/client'
import type { Entry } from './citationEntry'

/**
 * Which of the paper's stored `cites` references a reference-list entry is (D145), and what its card shows (D146).
 * Pure: it runs in the browser on the rows the References listing already returns.
 */

const MIN_TITLE_CHARS = 16
const MIN_TITLE_SCORE = 0.9
const DOI = /10\.\d{4,9}\/\S+/

/** The entry's identifiers as printed: lines joined with nothing, NFKC, lower case, no whitespace. Hyphens stay. */
export const idText = (entry: Pick<Entry, 'lines'>): string =>
  entry.lines.join('').normalize('NFKC').toLowerCase().replace(/\s+/g, '')

/** Letters and digits only, lower case, accents dropped: what a title score compares. */
export const squash = (text: string): string =>
  text.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')

function byDoi(ids: string, rows: Reference[]): Reference | null {
  // ponytail: a stored DOI that happens to be a prefix of the printed one would match. No such pair is known; add a
  // boundary check if one shows up.
  const hits = rows.filter((row) => row.doi && ids.includes(row.doi.toLowerCase()))
  // The longest wins, so a stored DOI that is a prefix of another printed one never beats it.
  return hits.sort((a, b) => b.doi!.length - a.doi!.length)[0] ?? null
}

function byArxiv(ids: string, rows: Reference[]): Reference | null {
  const printed = (id: string) =>
    new RegExp(`(?:arxiv[:.]|arxiv\\.org/(?:abs|pdf)/|abs/)${escapeRegExp(id.toLowerCase())}(?!\\d)`)
  return rows.find((row) => row.arxiv_id && printed(row.arxiv_id).test(ids)) ?? null
}

/**
 * The least edit distance between `pattern` and any stretch of `text` (Sellers' algorithm): the stretch may start and
 * end anywhere, so an entry's authors and venue cost nothing. One row of memory, local to this call.
 */
export function stretchDistance(pattern: string, text: string): number {
  const wanted = [...pattern]
  // row[i]: the fewest edits turning pattern[0..i] into a stretch of `text` that ends at the current character.
  const row = wanted.map((_, i) => i + 1)
  let best = wanted.length
  for (const char of text) {
    let diagonal = 0 // nothing of the pattern before this character: a stretch may start anywhere
    let shorter = 0
    for (let i = 0; i < wanted.length; i++) {
      const previous = row[i]
      row[i] = Math.min(diagonal + (wanted[i] === char ? 0 : 1), previous + 1, shorter + 1)
      diagonal = previous
      shorter = row[i]
    }
    best = Math.min(best, row[wanted.length - 1])
  }
  return best
}

/** 1 when the squashed title appears in the squashed entry, else one minus the distance over the title's length. */
export function titleScore(title: string, entryText: string): number {
  const [wanted, text] = [squash(title), squash(entryText)]
  if (text.includes(wanted)) return 1
  return 1 - stretchDistance(wanted, text) / wanted.length
}

function byTitle(text: string, rows: Reference[]): Reference | null {
  // ponytail: O(title × entry) per row, about 25 ms at REFS_CAP = 500 rows. Prefilter by shared words if a list ever
  // passes that.
  const scored = rows
    .filter((row) => squash(row.title).length >= MIN_TITLE_CHARS)
    .map((row) => ({ row, score: titleScore(row.title, text), length: squash(row.title).length }))
    .filter(({ score }) => score >= MIN_TITLE_SCORE)
  const best = scored.sort((a, b) => b.score - a.score || b.length - a.length || a.row.position - b.row.position)[0]
  return best?.row ?? null
}

/** D145: by DOI, else arXiv id, else title; null when none holds. `rows` are the paper's `cites` rows. */
export function matchEntry(entry: Entry, rows: Reference[]): Reference | null {
  const ids = idText(entry)
  return byDoi(ids, rows) ?? byArxiv(ids, rows) ?? byTitle(entry.text, rows)
}

/** The first DOI printed in `text`, trailing punctuation trimmed: an unmatched card's Open page. */
export function doiIn(text: string): string | null {
  const found = DOI.exec(text.normalize('NFKC').toLowerCase())
  return found ? found[0].replace(/[.,;)\]>]+$/, '') : null
}

/** What an unmatched card says about the paper's references, by their state (`error`: the listing itself failed). */
export const UNMATCHED_LINES = {
  none: "This paper's references haven't been looked up.",
  failed: "Looking up this paper's references failed.",
  fetching: "Looking up this paper's references…",
  ready: null,
  error: "Couldn't check your library for it.",
} as const

export type UnmatchedState = keyof typeof UNMATCHED_LINES

export type CardView =
  | { kind: 'loading' }
  | { kind: 'unreadable' }
  | { kind: 'in-library' | 'free-pdf' | 'details'; reference: Reference }
  | { kind: 'unmatched'; text: string; doi: string | null; state: UnmatchedState; openReferences: boolean }

/** D146: which of the card's states a citation shows, given the references listing. */
export function cardView(
  citation: { entry: Entry | null },
  references: Pick<UseQueryResult<References>, 'data' | 'isError'>,
): CardView {
  const { entry } = citation
  if (!entry) return { kind: 'unreadable' }
  const { data, isError } = references
  if (!data && !isError) return { kind: 'loading' }
  const reference = data ? matchEntry(entry, data.rows) : null
  if (reference?.paper_id) return { kind: 'in-library', reference }
  if (reference) return { kind: reference.has_pdf ? 'free-pdf' : 'details', reference }
  const state: UnmatchedState = data ? data.state : 'error'
  const openReferences = state === 'none' || state === 'failed'
  return { kind: 'unmatched', text: entry.text, doi: doiIn(entry.text), state, openReferences }
}
