import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type SectionReview } from '@/api/client'
import { citeThis } from './citeThis'
import type { ReviewHandle } from './reviewMarks'
import { marksFor } from './reviewModel'
import { staleReviews } from './sectionReviewModel'
import type { useReview } from './useReview'

const EDIT_MS = 600

type Args = {
  manuscriptId: string
  workspaceId: string | null
  review: Pick<ReturnType<typeof useReview>, 'items' | 'dismissed' | 'start'>
  /** The buffer's text now; null until the file has loaded. */
  text: string | null
  handle: ReviewHandle | null
  /** Saves what is pending first; resolves false when something is left unsaved. */
  flush: () => Promise<boolean>
  /** The file's updated_at as the last save left it. */
  getBase: () => string | null
  /** The open file's section reviews, to tell which sections changed since. */
  sections?: { file: string; reviews: SectionReview[] }
}

const NONE: SectionReview[] = []

/**
 * Where `items` sit in the text as it is now: asked at once after a fetch, after an edit once typing pauses; an answer
 * for text that has since moved on is dropped. Nothing is asked while there are no items.
 */
function useLocate<I, S>(items: I[], text: string | null, locate: (text: string) => Promise<S[]>) {
  const latest = useRef({ text, locate })
  useEffect(() => { latest.current = { text, locate } })
  const [located, setLocated] = useState<{ items: I[]; spans: S[] } | null>(null)
  const seen = useRef<I[] | null>(null)
  useEffect(() => {
    if (items.length === 0 || text === null) { seen.current = items; return }
    const fresh = seen.current !== items
    seen.current = items
    const timer = setTimeout(() => {
      const asked = latest.current.text
      if (asked === null) return
      latest.current.locate(asked).then(
        (spans) => { if (latest.current.text === asked) setLocated({ items, spans }) },
        () => {}, // the marks just stay where they are
      )
    }, fresh ? 0 : EDIT_MS)
    return () => clearTimeout(timer)
  }, [items, text])
  return located
}

/** Joins the stored results to the editor: re-anchors them on the text as it is, draws the marks, runs checks and "Cite this". */
export function useReviewInEditor({ manuscriptId, workspaceId, review, text, handle, flush, getBase, sections }: Args) {
  const { items, dismissed } = review
  const located = useLocate(items, text, (t) => api.locateSentences(manuscriptId, t).then((r) => r.sentences))
  const reviews = sections?.reviews ?? NONE
  const sectionSpans = useLocate(reviews, text, (t) => api.locateSections(manuscriptId, sections!.file, t).then((r) => r.sections))

  const joined = useMemo(
    () => (located && located.items === items ? marksFor(items, located.spans, dismissed) : { marks: [], stale: [] }),
    [located, items, dismissed],
  )
  useEffect(() => { handle?.setMarks(joined.marks) }, [handle, joined.marks])
  const sectionStale = useMemo(
    () => (sectionSpans && sectionSpans.items === reviews ? staleReviews(sectionSpans.spans, reviews) : []),
    [sectionSpans, reviews],
  )

  return {
    stale: joined.stale,
    /** Section reviews whose section has been edited (or removed) since. */
    sectionStale,
    jump: (hash: string) => handle?.reveal(hash),
    cite: (hash: string, paperId: string) => citeThis({ manuscriptId, workspaceId, handle }, hash, paperId),
    /** The selection when there is one (its unchecked sentences included), else the whole file. */
    check: async (confirmRemote = false) => {
      if (!(await flush())) return
      const base = getBase()
      if (!base) return
      const sel = handle?.selection()
      await review.start(base, sel ? { from: sel.from, to: sel.to, includeUncited: true } : undefined, confirmRemote).catch(() => {}) // the failure shows via startError or confirmHost
    },
  }
}
