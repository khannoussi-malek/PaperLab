import type { ProvNode } from '@/api/client'

export const YEAR_W = 60
export const LEVEL_H = 160
export const NO_YEAR_X = -YEAR_W * 2 // the narrow "No year" column, left of every year

/** A stable 0..1 from an id (the same id always lands in the same place). */
export function unit(id: string, salt = ''): number {
  let h = 5381
  for (const c of id + salt) h = (h * 33 + c.charCodeAt(0)) >>> 0
  return (h % 10007) / 10007
}

/** The visible papers with the most incoming paths (at least two; ties by id): the "key papers". */
export function keyPaperIds(nodes: ProvNode[], n = 10, hidden: Set<string> = new Set()): Set<string> {
  const pool = nodes.filter((p) => p.paths > 1 && !hidden.has(p.id))
  return new Set(pool.sort((a, b) => b.paths - a.paths || a.id.localeCompare(b.id)).slice(0, n).map((p) => p.id))
}

/** The year drawn at x = 0: the one origin the papers and the axis ticks share. */
export function mapOrigin(nodes: ProvNode[]): number {
  return Math.min(...nodes.flatMap((p) => (p.year ? [p.year] : [])))
}
export const tickX = (nodes: ProvNode[], year: number) => (year - mapOrigin(nodes)) * YEAR_W

/** One level band's height: the total height asked for split by level, else LEVEL_H each. */
export function bandHeight(nodes: ProvNode[], height?: number): number {
  const levels = Math.max(0, ...nodes.map((p) => p.level)) + 1
  return height ? height / levels : LEVEL_H
}

/** Fixed places, the same for the same data: x by year, y in the paper's level band, both jittered by a hash of the id. */
export function mapPositions(nodes: ProvNode[], height?: number): Map<string, { x: number; y: number }> {
  const minYear = mapOrigin(nodes)
  const band = bandHeight(nodes, height)
  return new Map(
    nodes.map((p) => [
      p.id,
      {
        x: (p.year ? (p.year - minYear) * YEAR_W : NO_YEAR_X) + (unit(p.id, 'x') - 0.5) * YEAR_W * 0.7,
        y: p.level * band + (unit(p.id, 'y') - 0.5) * band * 0.8,
      },
    ]),
  )
}

/** Year ticks for the axis: every 5th year in the span. */
export function yearTicks(nodes: ProvNode[]): number[] {
  const years = nodes.flatMap((p) => (p.year ? [p.year] : []))
  if (!years.length) return []
  const [lo, hi] = [Math.min(...years), Math.max(...years)]
  const first = Math.ceil(lo / 5) * 5
  return first > hi ? [lo] : Array.from({ length: Math.floor((hi - first) / 5) + 1 }, (_, i) => first + i * 5)
}
