import type { Note, Paper } from '@/api/client'

const counted = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

/** "6 papers · 31 notes", or "6 papers (1 not indexed) · 31 notes" when some papers can't be searched yet. */
export function countsLine(papers: number, notes: number, notIndexed = 0): string {
  const paperPart = counted(papers, 'paper') + (notIndexed > 0 ? ` (${notIndexed} not indexed)` : '')
  return `${paperPart} · ${counted(notes, 'note')}`
}

export type PaperNotes = { paper: Paper; notes: Note[] }

// Plain code-point order, not `localeCompare`'s locale-aware (roughly case-insensitive) collation: matches the
// backend's Python string comparison (core/workspaces.py), which sorts "BERT" before "attention…" since uppercase
// code points sort below lowercase. Using `localeCompare` here would pick a different anchor for a note on a tie.
const comparePlain = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0)

/**
 * A workspace's notes grouped by paper. A note linked to two of a workspace's papers shows once, under the one that
 * sorts first by `(title, id)`, plain comparison — matching the API's own order (core/workspaces.py), which also puts
 * the notes with no passage on that paper first. The API already returns notes in that order, so groups are built, and
 * kept, in the order it sent them. Papers with no notes are left out.
 */
export function notesByPaper(notes: Note[], papers: Paper[]): PaperNotes[] {
  const byId = new Map(papers.map((paper) => [paper.id, paper]))
  const groups = new Map<string, Note[]>()
  for (const note of notes) {
    const first = note.paper_ids
      .filter((paperId) => byId.has(paperId))
      .toSorted((a, b) => {
        const [pa, pb] = [byId.get(a)!, byId.get(b)!]
        return comparePlain(pa.title, pb.title) || comparePlain(pa.id, pb.id)
      })[0]
    if (first) groups.set(first, [...(groups.get(first) ?? []), note])
  }
  return [...groups].map(([paperId, grouped]) => ({ paper: byId.get(paperId)!, notes: grouped }))
}
