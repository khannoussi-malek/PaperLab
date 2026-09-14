import type { ChatSource } from '@/api/client'
import { MARKER } from './citations'

/** What "Save as note" sends. No chunk ids means there is nothing to anchor on, so saving is disabled. */
export type PromoteDraft = { body: string; chunkIds: string[] }

type Marker = { label: string; start: number; end: number }

const PARAGRAPH_BREAK = '\n\n'

const markersIn = (content: string): Marker[] =>
  [...content.matchAll(MARKER)].map((m) => ({ label: m[1], start: m.index, end: m.index + m[0].length }))

/** Chunk ids behind the markers, first seen first, skipping labels with no source or whose chunk is gone. */
function chunkIdsOf(markers: Marker[], sources: (ChatSource | null)[]): string[] {
  const ids = markers.flatMap(({ label }) => sources.find((s) => s?.label === label)?.chunk_id ?? [])
  return [...new Set(ids)]
}

/**
 * Maps a selection inside an answer (character offsets into its content, either order) to a note.
 * Anchors: the chunks cited inside the selection; else, if it cites only notes (`[N…]`), none; else those cited in the
 * paragraph the selection starts in; else none. Only `[C…]` markers ever anchor: a note citation has no chunk.
 * A marker the selection only partly covers counts and is included whole, so the body stays a verbatim slice of the
 * answer, which the API requires. Returns null for a blank selection.
 */
export function promoteSelection(
  content: string,
  sources: (ChatSource | null)[],
  anchor: number,
  focus: number,
): PromoteDraft | null {
  const markers = markersIn(content)
  const touched = markers.filter((m) => m.start < Math.max(anchor, focus) && m.end > Math.min(anchor, focus))
  const start = Math.min(anchor, focus, ...touched.map((m) => m.start))
  const end = Math.max(anchor, focus, ...touched.map((m) => m.end))
  const untrimmed = content.slice(start, end)
  const body = untrimmed.trim()
  if (!body) return null
  // The paragraph lookup uses where the body itself begins, not the raw (possibly whitespace) selection start:
  // a start sitting on the "\n" of the break before a paragraph must not be read as still inside the one before it.
  const trimmedStart = start + (untrimmed.length - untrimmed.trimStart().length)

  const selected = chunkIdsOf(touched, sources)
  if (selected.length > 0) return { body, chunkIds: selected }
  // A passage quoting the user's note isn't evidence from the paper, so the paragraph's passages mustn't stand in.
  if (touched.length > 0 && touched.every((m) => m.label.startsWith('N'))) return { body, chunkIds: [] }

  const breakBefore = content.lastIndexOf(PARAGRAPH_BREAK, trimmedStart - 1)
  const paragraphStart = breakBefore === -1 ? 0 : breakBefore + PARAGRAPH_BREAK.length
  const breakAfter = content.indexOf(PARAGRAPH_BREAK, trimmedStart)
  const paragraphEnd = breakAfter === -1 ? content.length : breakAfter
  const inParagraph = markers.filter((m) => m.start >= paragraphStart && m.end <= paragraphEnd)
  return { body, chunkIds: chunkIdsOf(inParagraph, sources) }
}
