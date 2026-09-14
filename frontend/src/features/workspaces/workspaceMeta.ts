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
 * A workspace's notes grouped by paper. A note anchored on two of a workspace's papers shows once, under the
 * anchor whose paper sorts first by `(title, id)`, plain comparison — matching the API's own tie-break
 * (core/workspaces.py). The API already returns notes sorted by that same key, so groups are built, and kept, in
 * the order the API sent them, rather than re-sorted here. Papers with no notes are left out.
 */
export function notesByPaper(notes: Note[], papers: Paper[]): PaperNotes[] {
  const byId = new Map(papers.map((paper) => [paper.id, paper]))
  const groups = new Map<string, Note[]>()
  for (const note of notes) {
    const onWorkspace = note.anchors.filter((anchor) => byId.has(anchor.paper_id))
    const first = onWorkspace.sort((a, b) => {
      const [pa, pb] = [byId.get(a.paper_id)!, byId.get(b.paper_id)!]
      return comparePlain(pa.title, pb.title) || comparePlain(pa.id, pb.id)
    })[0]
    if (first) groups.set(first.paper_id, [...(groups.get(first.paper_id) ?? []), note])
  }
  return [...groups].map(([paperId, grouped]) => ({ paper: byId.get(paperId)!, notes: grouped }))
}
