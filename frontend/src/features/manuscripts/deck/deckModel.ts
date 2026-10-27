import type { CitablePaper, Note } from '@/api/client'
import { latexEscape } from './latex'

/** The papers route's row, as the API returns it. */
export type DeckPaper = CitablePaper

export type BookItem = { id: string; kind: 'highlight' | 'note' | 'ai'; page: number | null; text: string; noteId: string }

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

export function insertText(item: BookItem | null, key: string): string {
  if (!item) return `\\citep{${key}}`
  if (item.kind === 'ai') return item.text.split('\n').map((l) => AI_PREFIX + l).join('\n')
  if (item.kind === 'highlight') return `\`\`${latexEscape(item.text)}'' \\citep[p.~${item.page}]{${key}}`
  return `${latexEscape(item.text)} \\citep{${key}}`
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
