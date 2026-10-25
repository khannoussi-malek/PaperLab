import { useEffect, useMemo, useRef, useState } from 'react'
import type { Chunk, LensId } from '@/api/client'
import { usePaperChunks, usePaperSections } from './queries'
import type { PdfRect } from '@/features/reader/coords'
import type { ReaderTab } from '@/lib/route'
import { fadeRects, lensRuns, stepRun } from './lenses'

/**
 * The reader's lens (spec §5): the picked lens (Full paper on opening, not remembered), its sections and chunks, the
 * fade on each page and the ◀ ▶ steps. `onJump` flashes a passage through the reader's one scroll path.
 */
export function useLensReader(paperId: string, tab: ReaderTab, onJump: (page: number, rects: PdfRect[]) => void) {
  const [lensId, setLensId] = useState<LensId>('full')
  const [runIndex, setRunIndex] = useState(0)
  const sectionsQuery = usePaperSections(paperId)
  const chunks = usePaperChunks(paperId, lensId !== 'full' || tab === 'lens')
  const lens = sectionsQuery.data?.lenses.find((option) => option.id === lensId) ?? null
  const inLens = useMemo(() => new Set(lens?.chunk_ids ?? []), [lens])
  const byPage = useMemo(() => groupByPage(chunks.data ?? []), [chunks.data])
  const runs = useMemo(() => (lensId === 'full' ? [] : lensRuns(chunks.data ?? [], inLens)), [lensId, chunks.data, inLens])

  function goTo(index: number) {
    setRunIndex(index)
    const run = runs[index]
    if (run) onJump(run.page, run.bbox)
  }

  // The first run of a lens, once its chunks and sections have loaded.
  function openFirstRun(id: LensId) {
    const target = sectionsQuery.data?.lenses.find((option) => option.id === id)
    if (!chunks.data || !target) return false
    const first = lensRuns(chunks.data, new Set(target.chunk_ids))[0]
    if (first) onJump(first.page, first.bbox)
    return true
  }

  // A picked lens opens on its first run; when its chunks are still loading, once they have.
  const pending = useRef<LensId | null>(null)
  useEffect(() => {
    if (pending.current && openFirstRun(pending.current)) pending.current = null
  })

  function pick(next: LensId) {
    setLensId(next)
    setRunIndex(0)
    pending.current = next === 'full' || openFirstRun(next) ? null : next
  }

  function jumpToChunk(chunkId: string) {
    const chunk = chunks.data?.find((candidate) => candidate.id === chunkId)
    if (chunk) onJump(chunk.page, chunk.bbox)
  }

  return {
    lensId,
    lens,
    lenses: sectionsQuery.data?.lenses ?? [],
    sections: sectionsQuery.data?.sections ?? [],
    sectionsQuery,
    chunks: chunks.data,
    runCount: runs.length,
    runIndex,
    pick,
    step: (delta: -1 | 1) => goTo(stepRun(runIndex, runs.length, delta)),
    fadeOn: (page: number): PdfRect[] => (lensId === 'full' ? [] : fadeRects(byPage.get(page) ?? [], inLens)),
    jumpToChunk,
    jump: onJump,
  }
}

export type LensReader = ReturnType<typeof useLensReader>

// ponytail: copies the map per chunk (quadratic in pages); fine at a few hundred chunks, one Map built in a loop if not.
function groupByPage(chunks: Chunk[]): Map<number, Chunk[]> {
  return chunks.reduce(
    (pages, chunk) => new Map(pages).set(chunk.page, [...(pages.get(chunk.page) ?? []), chunk]),
    new Map<number, Chunk[]>(),
  )
}
