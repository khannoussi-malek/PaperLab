import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type CheckItem, type ReviewSentence } from '@/api/client'
import { citeThis } from './citeThis'
import type { ReviewHandle } from './reviewMarks'
import { marksFor } from './reviewModel'
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
}

/** Joins the stored results to the editor: re-anchors them on the text as it is, draws the marks, runs checks and "Cite this". */
export function useReviewInEditor({ manuscriptId, workspaceId, review, text, handle, flush, getBase }: Args) {
  const { items, dismissed } = review
  const latest = useRef(text)
  useEffect(() => { latest.current = text })
  const [located, setLocated] = useState<{ items: CheckItem[]; spans: ReviewSentence[] } | null>(null)
  const seen = useRef<CheckItem[] | null>(null)

  // After a fetch at once, after an edit once typing pauses; an answer for text that has since moved on is dropped.
  useEffect(() => {
    if (items.length === 0 || text === null) { seen.current = items; return }
    const fresh = seen.current !== items
    seen.current = items
    const timer = setTimeout(() => {
      const asked = latest.current
      if (asked === null) return
      api.locateSentences(manuscriptId, asked).then(
        (r) => { if (latest.current === asked) setLocated({ items, spans: r.sentences }) },
        () => {}, // the marks just stay where they are
      )
    }, fresh ? 0 : EDIT_MS)
    return () => clearTimeout(timer)
  }, [items, text, manuscriptId])

  const joined = useMemo(
    () => (located && located.items === items ? marksFor(items, located.spans, dismissed) : { marks: [], stale: [] }),
    [located, items, dismissed],
  )
  useEffect(() => { handle?.setMarks(joined.marks) }, [handle, joined.marks])

  return {
    stale: joined.stale,
    jump: (hash: string) => handle?.reveal(hash),
    cite: (hash: string, paperId: string) => citeThis({ manuscriptId, workspaceId, handle }, hash, paperId),
    /** The selection when there is one (its unchecked sentences included), else the whole file. */
    check: async () => {
      if (!(await flush())) return
      const base = getBase()
      if (!base) return
      const sel = handle?.selection()
      await review.start(base, sel ? { from: sel.from, to: sel.to, includeUncited: true } : undefined).catch(() => {}) // the failure shows via startError
    },
  }
}
