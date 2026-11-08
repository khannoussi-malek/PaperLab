import type { ProvNode } from '@/api/client'

export const YEAR_W = 40
export const LEVEL_H = 90
export const STACK = 14
export const NO_YEAR_X = -YEAR_W * 3 // the "No year" lane, left of every year

/** The papers with the most incoming paths (ties by id): the "key papers". */
export function keyPaperIds(nodes: ProvNode[], n = 10): Set<string> {
  return new Set([...nodes].sort((a, b) => b.paths - a.paths || a.id.localeCompare(b.id)).slice(0, n).map((p) => p.id))
}

/** Fixed places, the same for the same data: x by year, y by level, papers sharing a year and level stacked by id. */
export function mapPositions(nodes: ProvNode[]): Map<string, { x: number; y: number }> {
  const years = nodes.flatMap((p) => (p.year ? [p.year] : []))
  const minYear = Math.min(...years)
  const cells = new Map<string, ProvNode[]>()
  for (const p of nodes) {
    const key = `${p.year ?? ''}|${p.level}`
    cells.set(key, [...(cells.get(key) ?? []), p])
  }
  const out = new Map<string, { x: number; y: number }>()
  for (const group of cells.values()) {
    group.sort((a, b) => a.id.localeCompare(b.id)).forEach((p, i) => {
      out.set(p.id, {
        x: p.year ? (p.year - minYear) * YEAR_W : NO_YEAR_X,
        y: p.level * LEVEL_H + (i - (group.length - 1) / 2) * STACK,
      })
    })
  }
  return out
}

/** Year ticks for the axis: every year for a short span, else every 5th. */
export function yearTicks(nodes: ProvNode[]): number[] {
  const years = nodes.flatMap((p) => (p.year ? [p.year] : []))
  if (!years.length) return []
  const [lo, hi] = [Math.min(...years), Math.max(...years)]
  const step = hi - lo > 15 ? 5 : 1
  return Array.from({ length: Math.floor((hi - lo) / step) + 1 }, (_, i) => lo + i * step)
}
