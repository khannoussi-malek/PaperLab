import type { CitablePaper, EvidenceRow, Note } from '@/api/client'
import { latexEscape } from './latex'

/** The papers route's row, as the API returns it. */
export type DeckPaper = CitablePaper

export type BookItem = { id: string; kind: 'highlight' | 'note' | 'ai' | 'evidence'; page: number | null; text: string; noteId: string; chunkId?: string }

// Mirrors backend manuscript_bib.cited_keys.
const CITE = /\\[A-Za-z]*[Cc]ite[A-Za-z]*\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]*)\}/g
const COMMENT = /(?<!\\)%.*/

export function citedKeys(texts: string[]): Set<string> {
  const found = new Set<string>()
  for (const text of texts) {
    const body = text.split(/\r?\n/).map((l) => l.replace(COMMENT, '')).join('\n')
    for (const m of body.matchAll(CITE)) {
      for (const k of m[1].split(',')) if (k.trim()) found.add(k.trim())
    }
  }
  return found
}

export function deckOrder(papers: DeckPaper[], inSection: Set<string>, elsewhere: Set<string>, ranked: string[]): DeckPaper[] {
  const rank = new Map(ranked.map((id, i) => [id, i]))
  const group = (p: DeckPaper) => (inSection.has(p.key) ? 0 : elsewhere.has(p.key) ? 1 : 2)
  const relevance = (p: DeckPaper) => rank.get(p.paper_id) ?? Infinity
  return [...papers].sort(
    (a, b) =>
      group(a) - group(b) ||
      (group(a) === 2 ? relevance(a) - relevance(b) || 0 : 0) ||
      a.title.localeCompare(b.title),
  )
}

export function bookItems(notes: Note[], paperId: string): BookItem[] {
  const items: BookItem[] = []
  for (const n of notes) {
    const mine = n.anchors.filter((a) => a.paper_id === paperId)
    if (!mine.length && !n.paper_ids.includes(paperId)) continue
    if (n.provenance !== 'human') {
      items.push({ id: `${n.id}:ai`, kind: 'ai', page: mine[0]?.page ?? null, text: n.body, noteId: n.id })
    } else if (mine.length) {
      mine.forEach((a, i) => items.push({ id: `${n.id}:h${i}`, kind: 'highlight', page: a.page, text: a.quoted_text, noteId: n.id }))
    } else {
      items.push({ id: `${n.id}:note`, kind: 'note', page: null, text: n.body, noteId: n.id })
    }
  }
  return items.sort(
    (a, b) => (a.page ?? Infinity) - (b.page ?? Infinity) || (a.noteId < b.noteId ? -1 : a.noteId > b.noteId ? 1 : 0),
  )
}

const AI_PREFIX = '% AI note (not your text): '

const BREAK = /\r\n|[\r\n\u2028\u2029\u0085]/
const BREAKS = /(?:\s*(?:\r\n|[\r\n\u2028\u2029\u0085])\s*)+/g
const UNSAFE_KEY = /[{}%\\\s]|^$/

export function insertText(item: BookItem | null, key: string): string {
  if (UNSAFE_KEY.test(key)) throw new Error(`Unsafe citation key: ${JSON.stringify(key)}`)
  if (!item || item.kind === 'evidence') return `\\citep{${key}}` // nothing from a passage or a verdict is ever inserted
  if (item.kind === 'ai') return item.text.split(BREAK).map((l) => AI_PREFIX + l).join('\n')
  const text = latexEscape(item.text.replace(BREAKS, ' '))
  if (item.kind === 'highlight') return `\`\`${text}'' \\citep[p.~${item.page}]{${key}}`
  return `${text} \\citep{${key}}`
}

export const turnDirection = (from: number, to: number): 'fwd' | 'bwd' => (to >= from ? 'fwd' : 'bwd')

export function cardTransform(offset: number): { transform: string; zIndex: number; opacity: number } {
  const a = Math.abs(offset)
  return {
    transform: `translateX(${offset * 95}px) translateZ(${-a * 120}px) rotateY(${-offset * 38}deg)`,
    zIndex: 10 - a,
    opacity: a > 2 ? 0 : 1,
  }
}

export function windowAround(n: number, current: number, radius = 3): number[] {
  const from = Math.max(0, current - radius)
  const to = Math.min(n - 1, current + radius)
  return Array.from({ length: Math.max(0, to - from + 1) }, (_, i) => from + i)
}

/** What the model said about one paper, as the book and the deck show it. `label` null = no verdict to show. */
export type VerdictView = { label: string | null; text: string; ai: boolean; quote: string | null; reason: string | null }

const VERDICT_LABEL: Record<string, string> = {
  supported: 'Supports',
  partially_supported: 'Partly supports',
  not_supported: "Doesn't support",
  not_addressed: "Doesn't address",
  cannot_verify: "Can't tell",
}
export const NO_MODEL = 'Add a model in Settings to get verdicts'

export function verdictView(row: EvidenceRow | undefined, unavailable: boolean): VerdictView {
  const plain = (text: string, label: string | null = text): VerdictView => ({ label, text, ai: false, quote: null, reason: null })
  if (unavailable) return plain(NO_MODEL, null)
  if (!row || row.status === 'queued' || row.status === 'running') return plain('Checking…')
  if (row.status !== 'done') return plain("Can't tell")
  const text = VERDICT_LABEL[row.verdict ?? ''] ?? "Can't tell"
  return { label: text, text, ai: true, quote: row.quote, reason: row.reason }
}

/** One blue E item per passage, in page order. */
export function evidenceItems(passages: { chunk_id: string; page: number; text: string }[]): BookItem[] {
  return passages
    .map((p) => ({ id: `${p.chunk_id}:e`, kind: 'evidence' as const, page: p.page, text: p.text, noteId: p.chunk_id, chunkId: p.chunk_id }))
    .sort((a, b) => a.page! - b.page!)
}

/** Papers with evidence first, in the order the evidence ranks them; the rest keep their order. */
export function evidenceFirst(ordered: DeckPaper[], evidenceIds: string[]): DeckPaper[] {
  const by = new Map(ordered.map((p) => [p.paper_id, p]))
  const first = evidenceIds.flatMap((id) => by.get(id) ?? [])
  const ids = new Set(first.map((p) => p.paper_id))
  return [...first, ...ordered.filter((p) => !ids.has(p.paper_id))]
}
