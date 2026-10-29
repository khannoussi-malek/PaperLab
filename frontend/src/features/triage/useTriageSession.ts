import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { api, type Paper, type TriageDecisionIn } from '@/api/client'
import { keys } from '@/api/queries'
import * as say from './announce'
import { buildDecision, type Pile } from './piles'
import { buildQueue, emptyQueue, progress, queueReducer, type DoneEntry, type Order } from './queue'
import { openSession } from './sessionId'
import { createWriter } from './triageWriter'

type Clock = { card_ms: number; pdf_ms: number; pdf_opened: boolean }
export type Alert = { message: string; retry?: () => void }
type Opts = {
  scope: string
  /** The list's filtered papers: used only to build and re-freeze the queue (and for `newSince`). */
  queueFrom: readonly Paper[]
  /** Every paper loaded for this scope, unfiltered: used for each card lookup and to spot papers deleted elsewhere. */
  library: readonly Paper[]
  /** False while `library` is loading or refetching with no data: nothing vanishes until it is true. */
  libraryReady: boolean
  filterKey: string
  order: Order
  includeDecided: boolean
}

const ELSEWHERE = 'This paper was changed elsewhere since. Open it to change it.'
const NEEDS_REASON = 'Pick a reason before marking a paper not relevant.'
const NO_CLOCK: Clock = { card_ms: 0, pdf_ms: 0, pdf_opened: false }
const reasonOf = (e: unknown) => (e instanceof Error ? e.message : 'something went wrong')

/**
 * The desk's whole session: the frozen queue, ordered writes (decide, skip, undo) and the alert and announcement text.
 * Two paper arrays: `queueFrom` (the list's filtered papers) only builds and re-freezes the stack; `library` (every paper
 * loaded for the scope, unfiltered) serves every card lookup, so a decided paper that leaves the filter can still be
 * undone. A paper missing from a ready, non-empty `library` is deleted elsewhere and leaves the session. */
export function useTriageSession({ scope, queueFrom, library, libraryReady, filterKey, order: initialOrder, includeDecided: initialInclude }: Opts) {
  const client = useQueryClient()
  const [sessionId] = useState(() => openSession(scope))
  const [order, setOrderState] = useState(initialOrder)
  const [includeDecided, setIncludeDecided] = useState(initialInclude)
  const seed = useRef(Math.floor(Math.random() * 2 ** 31))
  const [state, dispatch] = useReducer(queueReducer, emptyQueue, (s) =>
    queueReducer(s, { type: 'start', ids: buildQueue(queueFrom, { order, seed: seed.current, includeDecided, exclude: new Set() }).ids, seed: seed.current, order }),
  )
  const [alert, setAlert] = useState<Alert | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const [pending, setPending] = useState(0)

  // Latest values for callbacks that run after a write settles.
  const live = useRef({ state, queueFrom, library, order, includeDecided })
  live.current = { state, queueFrom, library, order, includeDecided }
  const pendingRef = useRef(0)
  // Text that leads the next new-card announcement; `exclusive` replaces it (an undo, a failure).
  const note = useRef<{ text: string; exclusive: boolean } | null>(null)
  const bodies = useRef(new Map<string, TriageDecisionIn>())
  const writer = useRef<ReturnType<typeof createWriter<DoneEntry>> | null>(null)
  writer.current ??= createWriter<DoneEntry>({
    post: async (entry) => {
      const body = bodies.current.get(entry.clientId)
      if (!body) throw new Error('missing decision body')
      return { eventId: (await api.decideTriage(entry.id, body)).event.id }
    },
    undo: (eventId) => api.undoTriage(eventId),
  })

  const paperOf = (id: string) => live.current.library.find((p) => p.id === id)
  const bump = (by: 1 | -1) => { pendingRef.current += by; setPending(pendingRef.current) }
  const invalidate = (paperId: string) =>
    Promise.all([
      client.invalidateQueries({ queryKey: keys.papers, exact: true }),
      client.invalidateQueries({ queryKey: keys.workspaces }),
      client.invalidateQueries({ queryKey: keys.graph }),
      client.invalidateQueries({ queryKey: keys.triageEvents(paperId) }),
    ])

  const write = useCallback((entry: DoneEntry) => {
    bump(1)
    void writer.current!.decide(entry).then((res) => {
      bump(-1)
      if (res.status === 'saved') {
        dispatch({ type: 'settle', clientId: entry.clientId, eventId: res.eventId })
        void invalidate(entry.id)
      } else if (res.status === 'failed') {
        // Only the live decision matters: one the reader already undid or made again is dropped silently.
        if (!live.current.state.done.some((d) => d.clientId === entry.clientId)) return
        const message = `Couldn't save: ${reasonOf(res.error)}`
        note.current = { text: say.failed(reasonOf(res.error)), exclusive: true }
        dispatch({ type: 'fail', clientId: entry.clientId })
        setAlert({
          message,
          retry: () => {
            setAlert(null)
            if (!live.current.state.unseen.includes(entry.id)) return
            dispatch({ type: 'decide', entry })
            write(entry)
          },
        })
        setAnnouncement(note.current.text)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const topOf = (s: typeof state, ps: readonly Paper[]) => ps.find((p) => p.id === s.unseen[0]) ?? null
  const top = topOf(state, library)
  const topId = top?.id ?? null

  const decide = useCallback((pile: Pile, o: { reason?: string; note?: string; clock?: Clock } = {}) => {
    const paper = topOf(live.current.state, live.current.library)
    if (!paper) return
    setAlert(null) // a stale failure alert must not outlive a new decision
    const clientId = crypto.randomUUID()
    let body: TriageDecisionIn
    try {
      body = buildDecision({ pile, sessionId, clientId, reason: o.reason, note: o.note, clock: o.clock ?? NO_CLOCK })
    } catch {
      setAlert({ message: NEEDS_REASON })
      return
    }
    bodies.current.set(clientId, body)
    const entry: DoneEntry = { id: paper.id, clientId, pile, before: { triage: paper.triage, pass: paper.reading_pass }, eventId: null, status: 'pending' }
    const { state: s } = live.current
    dispatch({ type: 'decide', entry })
    const text = say.decided(paper, pile, o.reason, progress(s).decided + (pile === 'skip' ? 0 : 1), s.total)
    note.current = { text, exclusive: false }
    setAnnouncement(text)
    write(entry)
  }, [sessionId, write])

  const undo = useCallback(() => {
    const entry = live.current.state.done.at(-1)
    if (!entry) return
    const paper = paperOf(entry.id)
    if (paper) {
      note.current = { text: say.undone(paper), exclusive: true }
      setAnnouncement(note.current.text)
    }
    dispatch({ type: 'undo' })
    bump(1)
    void writer.current!.undo(entry).then((res) => {
      bump(-1)
      if (res.status === 'saved') {
        void invalidate(entry.id)
      } else if (res.status === 'refused') {
        dispatch({ type: 'undoRefused', entry })
        setAlert({ message: ELSEWHERE })
        setAnnouncement(ELSEWHERE)
      } else if (res.status === 'failed') {
        // Re-decided meanwhile: the new decision stands, the old undo is moot.
        if (live.current.state.done.some((d) => d.id === entry.id)) return
        dispatch({ type: 'undoFailed', entry })
        setAlert({
          message: `Couldn't undo: ${reasonOf(res.error)}`,
          retry: () => {
            setAlert(null)
            if (live.current.state.done.at(-1)?.clientId === entry.clientId) undo()
          },
        })
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const skip = useCallback((clock?: Clock) => decide('skip', { clock }), [decide])

  const setOrder = useCallback((o: Order) => {
    setOrderState(o)
    dispatch({ type: 'reorder', order: o, papers: live.current.library })
  }, [])

  const reviewSkipped = useCallback(() => {
    if (pendingRef.current === 0) dispatch({ type: 'reviewSkipped' })
  }, [])

  // The filter or include-decided changed: rebuild the stack, keeping the session and what is already decided.
  const lastKey = useRef(`${filterKey}|${includeDecided}`)
  useEffect(() => {
    const key = `${filterKey}|${includeDecided}`
    if (lastKey.current === key) return // mount, or StrictMode's second mount
    lastKey.current = key
    const l = live.current
    dispatch({ type: 'refreeze', papers: l.queueFrom, opts: { order: l.order, seed: seed.current, includeDecided: l.includeDecided } })
  }, [filterKey, includeDecided])

  // Papers deleted elsewhere leave the session (keyed on the ids, not on every render).
  const queuedIds = state.unseen.concat(state.skipped).join(',')
  const liveIds = useMemo(() => new Set(library.map((p) => p.id)), [library])
  useEffect(() => {
    if (!libraryReady || liveIds.size === 0) return
    const gone = queuedIds === '' ? [] : queuedIds.split(',').filter((id) => !liveIds.has(id))
    if (gone.length) dispatch({ type: 'vanish', ids: gone })
  }, [queuedIds, liveIds, libraryReady])

  // Each new top card is announced, after the decision text that caused it (an undo or failure text stands alone).
  useEffect(() => {
    const { state: s, library: lib } = live.current
    const card = topOf(s, lib)
    const n = note.current
    note.current = null
    const next = card ? say.newCard(card, s.total - s.unseen.length, s.total) : ''
    const text = n?.exclusive ? n.text : [n?.text, next].filter(Boolean).join(' ')
    if (text) setAnnouncement(text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topId])

  const notReady = useMemo(() => buildQueue(queueFrom, { order, seed: seed.current, includeDecided, exclude: new Set() }).notReady, [queueFrom, order, includeDecided])

  return {
    state, top, sessionId, notReady, alert, announcement, pending, canReviewSkipped: pending === 0,
    decide, undo, skip, setOrder, setIncludeDecided, reviewSkipped, dismissAlert: () => setAlert(null),
  }
}
