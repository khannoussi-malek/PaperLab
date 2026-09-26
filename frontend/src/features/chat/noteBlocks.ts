import type { ChatSource, SavedNote } from '@/api/client'
import { noteHref, notesHref } from '@/lib/route'
import { promoteSelection, type PromoteDraft } from './promote'

/**
 * A piece of an answer: prose, a suggested note (numbered from 0 like the backend's blocks, empty ones included), or
 * the marker lines and blank space around a note, which render hidden. The parts tile the answer in order, so its text
 * stays whole and "Save as note" can keep counting offsets in it.
 */
export type NotePart =
  | { kind: 'prose' | 'marker'; start: number; end: number }
  | { kind: 'note'; index: number; start: number; end: number }

const OPEN = ':::note'
const CLOSE = ':::'
export const ALREADY_SAVED = 'already_saved'

/**
 * An answer cut the way backend `notes.note_blocks` reads it (same rules, tested on the same noteBlocks.cases.json): a
 * line that is exactly `:::note` once trimmed opens a block, one that is exactly `:::` closes it, the block's text is
 * its lines trimmed as a whole, a block not closed yet (one streaming in) runs to the end, and blocks don't nest.
 */
export function splitNoteBlocks(content: string): NotePart[] {
  const parts: NotePart[] = []
  let cursor = 0 // every character before it is in a part already
  let open: number | null = null // inside a block: where its text starts, just past the :::note line
  let index = 0
  const upTo = (kind: 'prose' | 'marker', end: number) => {
    if (end > cursor) parts.push({ kind, start: cursor, end })
    cursor = Math.max(cursor, end)
  }
  const block = (from: number, to: number) => {
    // The text is the block's lines trimmed as a whole; the space trimmed off belongs to the markers.
    const text = content.slice(from, to)
    const start = from + (text.length - text.trimStart().length)
    const end = Math.max(start, to - (text.length - text.trimEnd().length))
    upTo('marker', start)
    parts.push({ kind: 'note', index: index++, start, end })
    cursor = end
  }
  let at = 0
  for (const line of content.split('\n')) {
    const next = Math.min(at + line.length + 1, content.length) // past this line's \n
    if (open === null && line.trim() === OPEN) {
      upTo('prose', at)
      open = next
    } else if (open !== null && line.trim() === CLOSE) {
      block(open, Math.max(open, at - 1)) // the text ends before the \n that starts the close line
      upTo('marker', next)
      open = null
    }
    at = next
  }
  if (open !== null) block(open, content.length)
  upTo(open === null ? 'prose' : 'marker', content.length)
  return parts
}

/** A selection kept inside the prose or note part it starts in, so a saved body never takes in a marker line. Offsets
 * are into the whole answer; null when the selection starts past the last part. */
export function partSelection(
  parts: NotePart[],
  anchor: number,
  focus: number,
): { part: NotePart; start: number; end: number } | null {
  const [from, to] = anchor <= focus ? [anchor, focus] : [focus, anchor]
  const part = parts.find((p) => p.kind !== 'marker' && p.end > from)
  if (!part) return null
  const start = Math.max(from, part.start)
  return { part, start, end: Math.max(start, Math.min(to, part.end)) }
}

/** "Save as note" in an answer that may hold suggested notes: the selection kept to one part, then mapped as promote.ts
 * maps it within that part's text, so a card's paragraph never lends it another part's passages. */
export function promoteInPart(
  content: string,
  sources: (ChatSource | null)[],
  anchor: number,
  focus: number,
): PromoteDraft | null {
  const within = partSelection(splitNoteBlocks(content), anchor, focus)
  if (!within) return null
  const { part, start, end } = within
  return promoteSelection(content.slice(part.start, part.end), sources, start - part.start, end - part.start)
}

/** Where a saved suggestion's Open goes: the reader focused on the note, on the chat's paper while the note is still
 * on it, else on its first paper; with no paper, the Notes page's No paper list. */
export function savedNoteHref(saved: Pick<SavedNote, 'note_id' | 'paper_ids'>, chatPaperId: string | null): string {
  const paperId = chatPaperId !== null && saved.paper_ids.includes(chatPaperId) ? chatPaperId : saved.paper_ids.at(0)
  return paperId === undefined ? notesHref('none') : noteHref(paperId, saved.note_id)
}

const REFUSALS: Record<string, string> = {
  empty_body: 'This suggested note is empty, so there is nothing to save.',
  no_such_block: 'This suggested note is no longer in the saved answer.',
  answer_not_found: "This answer was deleted, so its notes can't be saved.",
}

/** A failed save in words; null for `already_saved`, since the card shows Saved once the history is refetched. A
 * dropped connection (fetch's TypeError) says nothing useful, so it gets a sentence of its own. */
export function suggestionError(error: Error): string | null {
  if (error.message === ALREADY_SAVED) return null
  if (error instanceof TypeError || !error.message) return "Couldn't save the note. Try again."
  return REFUSALS[error.message] ?? error.message
}
