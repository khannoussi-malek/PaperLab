import type { Paper } from '@/api/client'
import { quietStatus } from '@/features/library/paperMeta'
import { PILE_ORDER, type Pile } from './piles'

export type Order = 'oldest' | 'newest' | 'title' | 'year_desc' | 'year_asc' | 'cited' | 'list' | 'shuffle'

export const ORDERS: { value: Order; label: string }[] = [
  { value: 'oldest', label: 'Oldest added first' },
  { value: 'newest', label: 'Newest added first' },
  { value: 'title', label: 'Title A to Z' },
  { value: 'year_desc', label: 'Year, newest first' },
  { value: 'year_asc', label: 'Year, oldest first' },
  { value: 'cited', label: 'Most cited first' },
  { value: 'list', label: 'As in the list' },
  { value: 'shuffle', label: 'Shuffled' },
]

/** A paper the desk can show: ready, or one with no PDF that has nothing to ingest. */
export const isReady = (paper: Paper): boolean => quietStatus(paper)

function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Unknown numbers sort last whichever way the known ones go. */
const byNumber = (get: (p: Paper) => number | null, dir: 1 | -1) => (a: Paper, b: Paper) => {
  const x = get(a)
  const y = get(b)
  if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1
  return (x - y) * dir
}

const SORTS: Record<Exclude<Order, 'list' | 'shuffle'>, (a: Paper, b: Paper) => number> = {
  oldest: byNumber((p) => Date.parse(p.created_at), 1),
  newest: byNumber((p) => Date.parse(p.created_at), -1),
  title: (a, b) => a.title.localeCompare(b.title),
  year_desc: byNumber((p) => p.year, -1),
  year_asc: byNumber((p) => p.year, 1),
  cited: byNumber((p) => p.cited_by_count, -1),
}

/** Stable: ties keep their list position. */
export function orderPapers(papers: readonly Paper[], order: Order, seed: number): Paper[] {
  const out = [...papers]
  if (order === 'list') return out
  if (order === 'shuffle') {
    const rand = mulberry32(seed)
    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1))
      ;[out[i], out[j]] = [out[j], out[i]]
    }
    return out
  }
  return out.sort(SORTS[order]) // Array.sort is stable
}

export type QueueOpts = { order: Order; seed: number; includeDecided: boolean; exclude: ReadonlySet<string> }

export function buildQueue(papers: readonly Paper[], o: QueueOpts): { ids: string[]; notReady: number; failed: number } {
  let notReady = 0
  let failed = 0
  const eligible = papers.filter((p) => {
    if (o.exclude.has(p.id) || (!o.includeDecided && p.triage !== null)) return false
    if (isReady(p)) return true
    if (p.status === 'failed') failed++
    else notReady++
    return false
  })
  return { ids: orderPapers(eligible, o.order, o.seed).map((p) => p.id), notReady, failed }
}

export type DoneEntry = {
  id: string
  clientId: string
  pile: Pile
  before: { triage: Paper['triage']; pass: number }
  eventId: string | null
  status: 'pending' | 'saved'
}

export type QueueState = { unseen: string[]; skipped: string[]; done: DoneEntry[]; total: number; seed: number; order: Order }

export type QueueAction =
  | { type: 'start'; ids: string[]; seed: number; order: Order }
  | { type: 'decide'; entry: DoneEntry }
  | { type: 'settle'; clientId: string; eventId: string }
  | { type: 'fail'; clientId: string }
  | { type: 'undo' }
  | { type: 'undoFailed'; entry: DoneEntry }
  | { type: 'undoRefused'; entry: DoneEntry }
  | { type: 'reorder'; order: Order; papers: readonly Paper[] }
  | { type: 'refreeze'; papers: readonly Paper[]; opts: Omit<QueueOpts, 'exclude'> }
  | { type: 'reviewSkipped' }

export const emptyQueue: QueueState = { unseen: [], skipped: [], done: [], total: 0, seed: 0, order: 'oldest' }

const without = (list: readonly string[], id: string) => list.filter((x) => x !== id)
const decidedCount = (done: readonly DoneEntry[]) => done.filter((d) => d.pile !== 'skip').length
const withTotal = (s: QueueState): QueueState => ({ ...s, total: decidedCount(s.done) + s.skipped.length + s.unseen.length })

/** The card goes back on top of the stack (once), and out of the skipped list. */
const restore = (s: QueueState, entry: DoneEntry): QueueState => ({
  ...s,
  unseen: [entry.id, ...without(s.unseen, entry.id)],
  skipped: without(s.skipped, entry.id),
  done: s.done.filter((d) => d.clientId !== entry.clientId),
})

export function queueReducer(state: QueueState = emptyQueue, action: QueueAction): QueueState {
  switch (action.type) {
    case 'start':
      return { unseen: action.ids, skipped: [], done: [], total: action.ids.length, seed: action.seed, order: action.order }
    case 'decide': {
      const { entry } = action
      // A card decided again after "Review the skipped" replaces its old skip entry.
      const done = [...state.done.filter((d) => !(d.id === entry.id && d.pile === 'skip')), entry]
      return {
        ...state,
        unseen: without(state.unseen, entry.id),
        skipped: entry.pile === 'skip' ? [...without(state.skipped, entry.id), entry.id] : state.skipped,
        done,
      }
    }
    case 'settle':
      return {
        ...state,
        done: state.done.map((d) => (d.clientId === action.clientId ? { ...d, eventId: action.eventId, status: 'saved' } : d)),
      }
    case 'fail': {
      const entry = state.done.find((d) => d.clientId === action.clientId)
      return entry ? restore(state, entry) : state
    }
    case 'undo': {
      const entry = state.done.at(-1)
      return entry ? restore(state, entry) : state
    }
    case 'undoFailed':
      return {
        ...state,
        unseen: without(state.unseen, action.entry.id),
        skipped: action.entry.pile === 'skip' ? [...without(state.skipped, action.entry.id), action.entry.id] : state.skipped,
        done: [...state.done.filter((d) => d.clientId !== action.entry.clientId), action.entry],
      }
    case 'undoRefused':
      return {
        ...state,
        unseen: without(state.unseen, action.entry.id),
        skipped: without(state.skipped, action.entry.id),
        done: state.done.filter((d) => d.clientId !== action.entry.clientId),
      }
    case 'reorder': {
      const [head, ...rest] = state.unseen
      const tail = new Set(rest)
      const sorted = orderPapers(action.papers.filter((p) => tail.has(p.id)), action.order, state.seed).map((p) => p.id)
      const known = new Set(sorted)
      const unknown = rest.filter((id) => !known.has(id)) // deleted from the list meanwhile
      return { ...state, order: action.order, unseen: head === undefined ? [] : [head, ...sorted, ...unknown] }
    }
    case 'refreeze': {
      const exclude = new Set([...state.done.map((d) => d.id), ...state.skipped])
      const { ids } = buildQueue(action.papers, { ...action.opts, exclude })
      return withTotal({ ...state, unseen: ids, seed: action.opts.seed, order: action.opts.order })
    }
    case 'reviewSkipped':
      return { ...state, unseen: state.skipped, skipped: [] }
    default:
      return state // the stack is frozen: list refetches, uploads and reorders never reach it
  }
}

export const current = (s: QueueState): string | null => s.unseen[0] ?? null
export const progress = (s: QueueState) => ({ decided: decidedCount(s.done), skipped: s.skipped.length, total: s.total })
/** The stack is empty (skipped cards may still wait for review). */
export const isDone = (s: QueueState): boolean => s.unseen.length === 0

export function countsByPile(s: QueueState): Record<Pile, number> {
  const counts = Object.fromEntries(PILE_ORDER.map((p) => [p, 0])) as Record<Pile, number>
  for (const d of s.done) counts[d.pile]++
  return counts
}

/** Ready papers that arrived after the freeze: not in the stack, skipped or decided. */
export function newSince(s: QueueState, papers: readonly Paper[], o: { includeDecided: boolean }): number {
  const exclude = new Set([...s.unseen, ...s.skipped, ...s.done.map((d) => d.id)])
  return buildQueue(papers, { order: 'list', seed: 0, ...o, exclude }).ids.length
}
