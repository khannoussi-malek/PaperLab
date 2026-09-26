import type { Note, Paper } from '@/api/client'

/**
 * What Save will take away (N2): one line per unticked paper the note has a highlight on, naming the first page it is
 * on there. Linked with no highlight, a paper loses nothing you can see, so it gets no line.
 */
export function unlinkWarnings(
  note: Pick<Note, 'anchors'>,
  papers: Pick<Paper, 'id' | 'title'>[],
  ticked: readonly string[],
): string[] {
  const firstPage = new Map<string, number>()
  for (const { paper_id: paperId, page } of note.anchors) {
    if (!ticked.includes(paperId)) firstPage.set(paperId, Math.min(page, firstPage.get(paperId) ?? page))
  }
  const titles = new Map(papers.map((paper) => [paper.id, paper.title]))
  return [...firstPage].map(
    ([paperId, page]) => `Its highlight on p. ${page} in ${titles.get(paperId) ?? 'this paper'} will be removed.`,
  )
}
