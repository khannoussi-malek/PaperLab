import type { GraphLink, GraphNode } from '@/api/client'
import { CHART_INK, SERIES_COLORS, type ChartTheme } from '@/features/charts/palette'

export type LinkKind = GraphLink['kind']

/** Exactly the spec's wording, and the order the controls list them in. */
export const KIND_LABELS: Record<LinkKind, string> = {
  cites: 'Citations',
  same_workspace: 'Same workspace',
  co_anchored: 'Noted together',
  co_authored: 'Same author',
  shares_topic: 'Same topic',
  similar: 'Similar content',
  manual: 'Your links',
}

export const KINDS = Object.keys(KIND_LABELS) as LinkKind[]

/** P5: the two layers that say most about a library, without a hairball on first open. */
export const DEFAULT_LAYERS: LinkKind[] = ['cites', 'similar']

export const MIN_HOPS = 1
export const MAX_HOPS = 3
export const LABEL_MAX_CHARS = 80

/** A faded paper or link, outside the focus: every view draws it at this opacity. */
export const FADED = 0.12
export const MIN_RADIUS = 3
export const MAX_RADIUS = 9

export const EMPTY_LABEL = 'A link needs a short label, like "builds on".'
export const LABEL_TOO_LONG = `Keep the label under ${LABEL_MAX_CHARS} characters.`

export function layerCounts(links: GraphLink[]): Record<LinkKind, number> {
  const counts = Object.fromEntries(KINDS.map((kind) => [kind, 0])) as Record<LinkKind, number>
  for (const link of links) counts[link.kind] += 1
  return counts
}

export const visibleLinks = (links: GraphLink[], layers: LinkKind[]): GraphLink[] =>
  links.filter((link) => layers.includes(link.kind))

/**
 * A force-graph tooltip for untrusted text. force-graph hands a *string* label to float-tooltip, which sets it as
 * innerHTML, and a title comes from a PDF or a discovery source. An element whose textContent is the text can never
 * become markup.
 */
export function tooltipFor(text: string, doc: Pick<Document, 'createElement'> = document): HTMLElement {
  const element = doc.createElement('span')
  element.textContent = text
  return element
}

/**
 * The focused paper and everything within `hops` visible links of it, in either direction: a `cites` link points one
 * way on the canvas but still connects both papers. Breadth-first over a visited set, so a cycle ends.
 */
export function focusedIds(links: GraphLink[], focusId: string, hops: number): Set<string> {
  const neighbours = new Map<string, string[]>()
  const add = (from: string, to: string) => neighbours.set(from, [...(neighbours.get(from) ?? []), to])
  for (const link of links) {
    add(link.source, link.target)
    add(link.target, link.source)
  }
  const seen = new Set([focusId])
  let frontier = [focusId]
  for (let step = 0; step < hops && frontier.length > 0; step += 1) {
    const next = frontier.flatMap((id) => neighbours.get(id) ?? []).filter((id) => !seen.has(id))
    for (const id of next) seen.add(id)
    frontier = [...new Set(next)]
  }
  return seen
}

/**
 * A colour per workspace, from the charts palette (already checked for colour-blind readers on both surfaces). Taken
 * from every workspace, alphabetically — not from the papers on screen — so neither filtering by a workspace nor a
 * paper joining one moves a colour. A paper wears its *first* workspace's colour, and one with none the muted ink.
 * ponytail: the palette has six colours and cycles past the sixth; a seventh workspace shares a colour, which the
 * legend still names. Add colours to SERIES_COLORS if a library ever has that many workspaces.
 */
export function workspaceColors(names: readonly string[], theme: ChartTheme): Map<string, string> {
  const palette = SERIES_COLORS[theme]
  return new Map([...new Set(names)].sort().map((name, slot) => [name, palette[slot % palette.length]]))
}

export const nodeColor = (node: GraphNode, colors: Map<string, string>, theme: ChartTheme): string =>
  colors.get(node.workspaces[0] ?? '') ?? CHART_INK[theme].muted

export const NO_WORKSPACE = 'No workspace'

export type LegendEntry = { name: string; color: string }

/** The workspaces that colour a paper on screen, in colour order, then No workspace in the colour its papers wear. */
export function legendEntries(nodes: GraphNode[], colors: Map<string, string>, theme: ChartTheme): LegendEntry[] {
  const onScreen = new Set(nodes.map((node) => node.workspaces[0]))
  const named = [...colors].filter(([name]) => onScreen.has(name)).map(([name, color]) => ({ name, color }))
  const unfiled = nodes.some((node) => node.workspaces.length === 0)
  return unfiled ? [...named, { name: NO_WORKSPACE, color: CHART_INK[theme].muted }] : named
}

/** How many visible links touch each paper: the canvas sizes a node by it, the panel sorts by it. */
export function degrees(links: GraphLink[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const link of links) {
    counts.set(link.source, (counts.get(link.source) ?? 0) + 1)
    counts.set(link.target, (counts.get(link.target) ?? 0) + 1)
  }
  return counts
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

export const countsLine = (papers: number, links: number) => `${plural(papers, 'paper')}, ${plural(links, 'link')}`

/** The message the API would send, or null. Checked here so the dialog can say it before the request goes out. */
export function labelError(label: string): string | null {
  const trimmed = label.trim()
  if (trimmed.length === 0) return EMPTY_LABEL
  if (trimmed.length > LABEL_MAX_CHARS) return LABEL_TOO_LONG
  return null
}

/** A canvas paper: its colour, and a radius from MIN_RADIUS to MAX_RADIUS by its share of the visible links. */
export type SizedNode = GraphNode & { color: string; radius: number }

export function sizedNodes(
  nodes: GraphNode[],
  links: GraphLink[],
  colors: Map<string, string>,
  theme: ChartTheme
): SizedNode[] {
  const degree = degrees(links)
  const busiest = Math.max(1, ...degree.values())
  return nodes.map((node) => ({
    ...node,
    color: nodeColor(node, colors, theme),
    radius: MIN_RADIUS + ((MAX_RADIUS - MIN_RADIUS) * (degree.get(node.id) ?? 0)) / busiest,
  }))
}

/** Where force-graph left a paper: it writes x/y (and z in 3D) onto the node objects it is given. */
export type Placed = { id: string; x?: number; y?: number; z?: number }

type Motion = { x?: number; y?: number; z?: number; vx?: number; vy?: number; vz?: number }

/**
 * K20: a rebuilt graph (a layer toggled, the theme flipped, a link saved) starts each surviving paper where it was,
 * at rest, instead of throwing the whole layout again. A new paper gets no position, so the simulation places it.
 */
export function carryPositions<T extends { id: string }>(next: readonly T[], previous: readonly Placed[]): (T & Motion)[] {
  const was = new Map(previous.map((node) => [node.id, node]))
  return next.map((node) => {
    const old = was.get(node.id)
    if (old?.x === undefined || old.y === undefined) return node
    const depth = old.z === undefined ? {} : { z: old.z, vz: 0 }
    return { ...node, x: old.x, y: old.y, vx: 0, vy: 0, ...depth }
  })
}

/** A hex colour at an opacity, so one palette serves both the faded and the solid state. */
export function withAlpha(hex: string, alpha: number): string {
  const value = Number.parseInt(hex.slice(1), 16)
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`
}

/** force-graph swaps a link's string ids for node objects once the simulation runs. */
export const endId = (end: string | { id: string }): string => (typeof end === 'string' ? end : end.id)
