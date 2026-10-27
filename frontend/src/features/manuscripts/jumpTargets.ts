import type { CitablePaper } from '@/api/client'
import { COMMENT, crumbsAt, type OutlineItem } from './outline'
import type { SectionRow } from './sections'

export type Target =
  | { id: string; kind: 'section' | 'heading' | 'label'; label: string; detail: string; file: string; line: number }
  | { id: string; kind: 'paper'; label: string; detail: string; key: string }

const LABEL = /\\label\s*\{([^}]*)\}/g

/** Everything the palette can jump to: sections, deeper headings, \label{}s (with their heading) and papers. */
export function jumpTargets(rows: SectionRow[], items: OutlineItem[], texts: Record<string, string>, papers: CitablePaper[]): Target[] {
  const out: Target[] = []
  for (const r of rows) if (!r.missing) out.push({ id: `s:${r.path}:${r.line}`, kind: 'section', label: r.title, detail: r.path, file: r.path, line: r.inMain ? r.line : 1 })
  for (const it of items) if (!rows.some((r) => r.path === it.file && r.title === it.title)) out.push({ id: `h:${it.file}:${it.line}`, kind: 'heading', label: it.title, detail: it.file, file: it.file, line: it.line })
  for (const [file, text] of Object.entries(texts)) {
    text.split('\n').forEach((raw, i) => {
      for (const m of raw.replace(COMMENT, '$1').matchAll(LABEL)) {
        const under = crumbsAt(items, file, i + 1).at(-1)
        out.push({ id: `l:${file}:${i + 1}:${m[1]}`, kind: 'label', label: m[1].trim(), detail: under ? `${under.title} (${file})` : file, file, line: i + 1 })
      }
    })
  }
  for (const p of papers) out.push({ id: `p:${p.paper_id}`, kind: 'paper', label: p.title, detail: [p.first_author, p.year].filter(Boolean).join(' '), key: p.key })
  return out
}
