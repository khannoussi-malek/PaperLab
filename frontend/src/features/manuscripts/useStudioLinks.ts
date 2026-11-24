import { useCallback, useRef, useState } from 'react'
import type { PreambleEdit } from '@/features/manuscripts/results/insertBlock'

/** What the editor, the Papers column and the PDF hand each other: registered handles, cited keys, evidence asks and column reveals. */
export function useStudioLinks() {
  const replaceRef = useRef<((line: number, start: number, end: number, text: string) => void) | null>(null)
  const registerReplace = useCallback((f: typeof replaceRef.current) => { replaceRef.current = f }, [])
  const insertRef = useRef<((text: string, block?: boolean, preamble?: PreambleEdit) => void) | null>(null)
  const registerInsert = useCallback((f: typeof insertRef.current) => { insertRef.current = f }, [])
  const hasEditor = () => !!insertRef.current
  const insertAtCursor = useCallback((text: string, block = false, preamble?: PreambleEdit) => {
    if (!insertRef.current) return false
    insertRef.current(text, block, preamble)
    return true
  }, [])
  const findRef = useRef<(() => boolean) | null>(null)
  const registerFindEvidence = useCallback((f: typeof findRef.current) => { findRef.current = f }, [])
  const findFromDeck = useCallback(() => findRef.current?.() ?? false, [])
  const [openKey, setOpenKey] = useState<{ key: string; n: number } | null>(null)
  const [evidenceAsk, setEvidenceAsk] = useState<{ doc: string; from: number; to: number; n: number } | null>(null)
  const [reveal, setReveal] = useState<{ id: string; n: number } | null>(null)
  const showCited = useCallback((key: string) => {
    setOpenKey((k) => ({ key, n: (k?.n ?? 0) + 1 }))
    setReveal((r) => ({ id: 'papers', n: (r?.n ?? 0) + 1 }))
  }, [])
  const asks = useRef(0) // never restarts, so an ask after Clear is never mistaken for one the deck already ran
  const findEvidence = useCallback((doc: string, from: number, to: number) => {
    setEvidenceAsk({ doc, from, to, n: ++asks.current })
    setReveal((r) => ({ id: 'papers', n: (r?.n ?? 0) + 1 }))
  }, [])
  const clearEvidence = useCallback(() => setEvidenceAsk(null), []) // a remounted deck must not ask it again
  // Only an explicit Show in PDF brings the PDF forward (its tab, when it shares one with Papers); following a compile never does.
  const revealPdf = useCallback(() => setReveal((r) => ({ id: 'pdf', n: (r?.n ?? 0) + 1 })), [])
  return {
    replaceRef, registerReplace, registerInsert, hasEditor, insertAtCursor, registerFindEvidence, findFromDeck,
    openKey, evidenceAsk, reveal, showCited, findEvidence, clearEvidence, revealPdf,
  }
}
