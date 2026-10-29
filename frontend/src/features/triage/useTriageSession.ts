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
type Opts = { scope: string; papers: readonly Paper[]; filterKey: string; order: Order; includeDecided: boolean }

const ELSEWHERE = 'This paper was changed elsewhere since. Open it to change it.'
const NEEDS_REASON = 'Pick a reason before marking a paper not relevant.'
const NO_CLOCK: Clock = { card_ms: 0, pdf_ms: 0, pdf_opened: false }
const reasonOf = (e: unknown) => (e instanceof Error ? e.message : 'something went wrong')

/** The desk's whole session: the frozen queue, ordered writes (decide, skip, undo) and the alert and announcement text. */
export function useTriageSession({ scope, papers, filterKey, order: initialOrder, includeDecided: initialInclude }: Opts) {
  const client = useQueryClient()
  const [sessionId] = useState(() => openSession(scope))
  const [order, setOrderState] = useState(initialOrder)
  const [includeDecided, setIncludeDecided] = useState(initialInclude)
  const seed = useRef(Math.floor(Math.random() * 2 ** 31))
  const [state, dispatch] = useReducer(queueReducer, emptyQueue, (s) =>
    queueReducer(s, { type: 'start', ids: buildQueue(papers, { order, seed: seed.current, includeDecided, exclude: new Set() }).ids, seed: seed.current, order }),
  )
  const [alert, setAlert] = useState<Alert | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const [pending, setPending] = useState(0)

  // Latest values for callbacks that run after a write settles.
  const live = useRef({ state, papers, order, includeDecided })
  live.current = { state, papers, order, includeDecided }
  const pendingRef = useRef(0)
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

  const paperOf = (id: string) => live.current.papers.find((p) => p.id === id)
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
        dispatch({ type: 'fail', clientId: entry.clientId })
        const message = `Couldn't save: ${reasonOf(res.error)}`
        setAlert({ message, retry: () => { setAlert(null); dispatch({ type: 'decide', entry }); write(entry) } })
        setAnnouncement(say.failed(reasonOf(res.error)))
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const topId = state.unseen.find((id) => papers.some((p) => p.id === id)) ?? null
  const top = papers.find((p) => p.id === topId) ?? null

  const decide = useCallback((pile: Pile, o: { reason?: string; note?: string; clock?: Clock } = {}) => {
    const paper = top
    if (!paper) return
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
    setAnnouncement(say.decided(paper, pile, o.reason, progress(s).decided + (pile === 'skip' ? 0 : 1), s.total))
    write(entry)
  }, [top, sessionId, write])

  const undo = useCallback(() => {
    const entry = live.current.state.done.at(-1)
    if (!entry) return
    dispatch({ type: 'undo' })
    bump(1)
    void writer.current!.undo(entry).then((res) => {
      bump(-1)
      if (res.status === 'saved') {
        void invalidate(entry.id)
        const paper = paperOf(entry.id)
        if (paper) setAnnouncement(say.undone(paper))
      } else if (res.status === 'refused') {
        dispatch({ type: 'undoRefused', entry })
        setAlert({ message: ELSEWHERE })
        setAnnouncement(ELSEWHERE)
      } else if (res.status === 'failed') {
        dispatch({ type: 'undoFailed', entry })
        setAlert({ message: `Couldn't undo: ${reasonOf(res.error)}`, retry: () => { setAlert(null); undo() } })
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const skip = useCallback((clock?: Clock) => decide('skip', { clock }), [decide])

  const setOrder = useCallback((o: Order) => {
    setOrderState(o)
    dispatch({ type: 'reorder', order: o, papers: live.current.papers })
  }, [])

  const reviewSkipped = useCallback(() => {
    if (pendingRef.current === 0) dispatch({ type: 'reviewSkipped' })
  }, [])

  // The filter or include-decided changed: rebuild the stack, keeping the session and what is already decided.
  const first = useRef(true)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    const l = live.current
    dispatch({ type: 'refreeze', papers: l.papers, opts: { order: l.order, seed: seed.current, includeDecided: l.includeDecided } })
  }, [filterKey, includeDecided])

  const notReady = useMemo(() => buildQueue(papers, { order, seed: seed.current, includeDecided, exclude: new Set() }).notReady, [papers, order, includeDecided])

  return {
    state, top, sessionId, notReady, alert, announcement, pending, canReviewSkipped: pending === 0,
    decide, undo, skip, setOrder, setIncludeDecided, reviewSkipped, dismissAlert: () => setAlert(null),
  }
}
