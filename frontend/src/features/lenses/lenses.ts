import type { Chunk, Lens, Role, Section } from '@/api/client'
import { refusal, type ChatProblem } from '@/features/chat/refusals'
import type { PdfRect } from '@/features/reader/coords'

/** Each role in words: the Lens tab's chips and its Change role menu. `Record` makes tsc name a role the API adds. */
export const ROLE_LABEL: Record<Role, string> = {
  abstract: 'Abstract',
  intro: 'Introduction',
  related: 'Related work',
  method: 'Method',
  results: 'Results',
  discussion: 'Discussion',
  limitations: 'Limitations',
  conclusion: 'Conclusion',
  back: 'Back matter',
  other: 'Other',
}

/** Where a chunk sits: what fading and jumping need. */
type Placed = Pick<Chunk, 'id' | 'page' | 'bbox'>

/**
 * The rects to fade on one page: those of every chunk outside the lens. Headings and figures are no chunk's rects, so
 * they stay readable as signposts (spec §5, D122).
 */
export function fadeRects(pageChunks: Placed[], lensChunkIds: ReadonlySet<string>): PdfRect[] {
  return pageChunks.filter((chunk) => !lensChunkIds.has(chunk.id)).flatMap((chunk) => chunk.bbox)
}

/** The first chunk of each run of consecutive lens chunks, in reading order: where each ◀ ▶ step lands. */
export function lensRuns<T extends Pick<Chunk, 'id'>>(chunks: T[], lensChunkIds: ReadonlySet<string>): T[] {
  return chunks.filter((chunk, i) => lensChunkIds.has(chunk.id) && (i === 0 || !lensChunkIds.has(chunks[i - 1].id)))
}

/** The run a step lands on, from `index` among `count`, never past either end. */
export function stepRun(index: number, count: number, delta: -1 | 1): number {
  return Math.min(Math.max(index + delta, 0), Math.max(count - 1, 0))
}

export type LensNotice = { kind: 'no_pdf' | 'empty' | 'fallback' | 'missing'; text: string }

/** A paper without a PDF has no sections, so every lens is empty and none of the section notices apply (R1). */
export const NO_PDF_LENS_TEXT = "Lenses read a paper's sections. Attach its PDF to use them."

/** `headed`: the paper has a heading. Without one Full paper has no Change role menu, so the hint is dropped. */
export const emptyLensText = (label: string, headed = true) =>
  `This paper has no sections for ${label}.${headed ? " Switch to Full paper to fix a section's role." : ''}`

/** Whether any section has a heading, so a role can be fixed in Full paper. */
export const hasHeadings = (sections: Pick<Section, 'title'>[]) => sections.some((section) => section.title !== null)

type NoticeFields = Pick<Lens, 'id' | 'label' | 'chunk_ids' | 'positional_fallback' | 'missing_roles'>

/** What the Lens tab says above a lens's sections, if anything (spec §2). Without a PDF it says only that. */
export function lensNotice(lens: NoticeFields, hasPdf = true, headed = true): LensNotice | null {
  if (!hasPdf) return { kind: 'no_pdf', text: NO_PDF_LENS_TEXT }
  if (lens.id === 'full') return null
  if (lens.chunk_ids.length === 0) return { kind: 'empty', text: emptyLensText(lens.label, headed) }
  if (lens.positional_fallback) {
    return { kind: 'fallback', text: 'No Introduction or Conclusion headings found. Showing the start and end of the paper.' }
  }
  if (lens.id === 'critical' && lens.missing_roles.includes('limitations')) {
    return { kind: 'missing', text: 'No limitations section found in this paper.' }
  }
  return null
}

/** The sections a lens lists: every one for Full paper, else those with a chunk in the lens. */
export function lensSections(sections: Section[], lens: Pick<Lens, 'id' | 'chunk_ids'>): Section[] {
  if (lens.id === 'full') return sections
  const inLens = new Set(lens.chunk_ids)
  return sections.filter((section) => section.chunk_ids.some((id) => inLens.has(id)))
}

/** A brief refused before streaming, in words: an empty lens as the Lens tab says it, the rest as chat does. */
export function briefProblem(status: number, detail: string, lensLabel: string): ChatProblem {
  if (detail === 'lens_empty') return { message: emptyLensText(lensLabel), retryable: false, reindex: false }
  if (detail === 'needs_full_text') return { message: NO_PDF_LENS_TEXT, retryable: false, reindex: false }
  if (detail === 'no_model') return { message: 'Add a model in Settings to write briefs.', retryable: false, reindex: false, settings: true }
  return refusal(status, detail)
}
