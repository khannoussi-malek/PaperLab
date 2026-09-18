import type { GraphLink, GraphNode } from '@/api/client'
import { KIND_LABELS, type LinkKind } from './graphModel'

export type TimeAxis = 'published' | 'added'

export const TIME_AXIS_LABELS: Record<TimeAxis, string> = { published: 'Year published', added: 'Date added' }
export const UNKNOWN_LANE = 'Year unknown'
export const MISSING_YEARS_HINT = 'Turn on OpenAlex in Settings to fill in missing years.'

export type TimelineDot = { node: GraphNode; x: number; y: number }
export type TimelineArc = { source: string; target: string; kind: LinkKind; path: string; title: string }
export type TimelineTick = { x: number; label: string }
export type TimelineLayout = {
  dots: TimelineDot[]
  arcs: TimelineArc[]
  ticks: TimelineTick[]
  axisY: number
  /** Some paper has no year, so the Year published axis has an unknown lane (never on Date added). */
  hasUnknown: boolean
}

type Column = { x: number; papers: GraphNode[] }
type Axis = { columns: Column[]; ticks: TimelineTick[]; hasUnknown: boolean }

const SIDE = 48
const TOP = 16
const BOTTOM = 32
const STEP = 16
const SAME_COLUMN_BOW = 24
const DAY_MS = 86_400_000
// English like the rest of the page; UTC so a paper added late in the evening lands in one month for every viewer.
const MONTH = new Intl.DateTimeFormat('en', { month: 'short', year: 'numeric', timeZone: 'UTC' })

const byTitle = (a: GraphNode, b: GraphNode) => a.title.localeCompare(b.title)

/**
 * The Timeline (spec §5.4), in pixels for a box of `width` × `height`: papers as dots stacked upwards from the axis
 * (by title), links as arcs above it between two dots, higher the further apart.
 * ponytail: SVG with one element per paper and link is fine into the low thousands; beyond that, draw on a canvas.
 */
export function timelineLayout(
  nodes: GraphNode[],
  links: GraphLink[],
  axis: TimeAxis,
  box: { width: number; height: number }
): TimelineLayout {
  const axisY = box.height - BOTTOM
  const { columns, ticks, hasUnknown } = axis === 'published' ? byYear(nodes, box.width) : byDay(nodes, box.width)
  const tallest = Math.max(1, ...columns.map((column) => column.papers.length))
  // A tall stack squeezes to fit under the top of the box instead of running off it.
  const step = Math.min(STEP, (axisY - TOP) / tallest)
  const dots = columns.flatMap(({ x, papers }) =>
    [...papers].sort(byTitle).map((node, index) => ({ node, x, y: axisY - step * (index + 1) }))
  )
  const at = new Map(dots.map((dot) => [dot.node.id, dot]))
  const arcs = links.flatMap((link) => {
    const from = at.get(link.source)
    const to = at.get(link.target)
    return from && to ? [arc(link, from, to)] : []
  })
  return { dots, arcs, ticks, axisY, hasUnknown }
}

/** One slot per year from the first to the last (empty years keep their tick), then the unknown lane if needed. */
function byYear(nodes: GraphNode[], width: number): Axis {
  const years = nodes.flatMap((node) => (node.year === null ? [] : [node.year]))
  const first = Math.min(...years)
  const span = years.length === 0 ? 0 : Math.max(...years) - first + 1
  const undated = nodes.filter((node) => node.year === null)
  const hasUnknown = undated.length > 0
  const slots = span + (hasUnknown ? 1 : 0)
  const x = (slot: number) => SIDE + ((slot + 0.5) * (width - 2 * SIDE)) / slots
  const axisYears = Array.from({ length: span }, (_, offset) => first + offset)
  const columns = axisYears.map((year, slot) => ({ x: x(slot), papers: nodes.filter((node) => node.year === year) }))
  const ticks = axisYears.map((year, slot) => ({ x: x(slot), label: String(year) }))
  if (!hasUnknown) return { columns, ticks, hasUnknown }
  return {
    columns: [...columns, { x: x(span), papers: undated }],
    ticks: [...ticks, { x: x(span), label: UNKNOWN_LANE }],
    hasUnknown,
  }
}

/** Time from the first day a paper was added to the last; papers added the same (UTC) day stack like one year. */
function byDay(nodes: GraphNode[], width: number): Axis {
  const dayOf = (node: GraphNode) => Math.floor(Date.parse(node.added_at) / DAY_MS) * DAY_MS
  const days = [...new Set(nodes.map(dayOf))].sort((a, b) => a - b)
  const first = days[0] ?? 0
  const last = days.at(-1) ?? 0
  const x = (time: number) => (last === first ? width / 2 : SIDE + ((time - first) / (last - first)) * (width - 2 * SIDE))
  const columns = days.map((day) => ({ x: x(day), papers: nodes.filter((node) => dayOf(node) === day) }))
  return { columns, ticks: monthTicks(first, last, x), hasUnknown: false }
}

/** A tick at the start of the axis, named after its month, then one at every month start inside the span. */
function monthTicks(first: number, last: number, x: (time: number) => number): TimelineTick[] {
  const start = new Date(first)
  const end = new Date(last)
  const months = (end.getUTCFullYear() - start.getUTCFullYear()) * 12 + end.getUTCMonth() - start.getUTCMonth()
  const later = Array.from({ length: months }, (_, n) =>
    Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + n + 1, 1)
  )
  return [first, ...later].map((time) => ({ x: x(time), label: MONTH.format(time) }))
}

/** A quadratic arc above the axis, from the link's source to its target, rising half the distance between them. */
function arc(link: GraphLink, from: TimelineDot, to: TimelineDot): TimelineArc {
  const apart = Math.abs(to.x - from.x)
  // Two papers in one column bow sideways instead of drawing a line through the stack between them.
  const cx = apart === 0 ? from.x + SAME_COLUMN_BOW : (from.x + to.x) / 2
  const cy = Math.max(0, Math.min(from.y, to.y) - apart / 2)
  const label = link.label ? ` (${link.label})` : ''
  return {
    source: link.source,
    target: link.target,
    kind: link.kind,
    path: `M ${from.x} ${from.y} Q ${cx} ${cy} ${to.x} ${to.y}`,
    title: `${from.node.title} and ${to.node.title}: ${KIND_LABELS[link.kind]}${label}`,
  }
}
