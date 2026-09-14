import type { Note, Paper } from '@/api/client'

const counted = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

/** "6 papers · 31 notes", or "6 papers (1 not indexed) · 31 notes" when some papers can't be searched yet. */
export function countsLine(papers: number, notes: number, notIndexed = 0): string {
  const paperPart = counted(papers, 'paper') + (notIndexed > 0 ? ` (${notIndexed} not indexed)` : '')
  return `${paperPart} · ${counted(notes, 'note')}`
}

export type PaperNotes = { paper: Paper; notes: Note[] }

/**
 * A workspace's notes grouped by paper, papers in title order. A note anchored on two of a
 * workspace's papers shows once, under the anchor whose paper sorts first by title — matching the API's own order
 * (core/workspaces.py). Within a paper, notes keep the API's reading order. Papers with no notes are left out.
 */
export function notesByPaper(notes: Note[], papers: Paper[]): PaperNotes[] {
  const byId = new Map(papers.map((paper) => [paper.id, paper]))
  const groups = new Map<string, Note[]>()
  for (const note of notes) {
    const onWorkspace = note.anchors.filter((anchor) => byId.has(anchor.paper_id))
    const first = onWorkspace.sort((a, b) => byId.get(a.paper_id)!.title.localeCompare(byId.get(b.paper_id)!.title))[0]
    if (first) groups.set(first.paper_id, [...(groups.get(first.paper_id) ?? []), note])
  }
  return [...groups]
    .map(([paperId, grouped]) => ({ paper: byId.get(paperId)!, notes: grouped }))
    .sort((a, b) => a.paper.title.localeCompare(b.paper.title))
}
