import type { GraphLink, GraphNode } from '@/api/client'
import { sequentialScale, type ChartTheme } from '@/features/charts/palette'
import { byFirstWorkspace, degrees, KIND_LABELS, KINDS, type LinkKind } from './graphModel'

/** D114: 50 × 50 is 2,500 cells, readable on a laptop screen; a bigger grid can't be read anyway. */
export const MATRIX_CAP = 50
export const MATRIX_CAP_LINE = `Showing the ${MATRIX_CAP} most connected papers.`
export const MATRIX_CAPTION = 'Links between your papers'
/** What a paper's cell with itself reads. */
export const DIAGONAL = '—'

export type MatrixCell = { kinds: LinkKind[]; name: string; color: string }

export type Matrix = {
  papers: GraphNode[]
  /** cells[row][column], in `papers` order: null on the diagonal and where no visible link joins the pair. */
  cells: (MatrixCell | null)[][]
  /** More papers than MATRIX_CAP were on screen, so the least connected were left out. */
  capped: boolean
}

/** "Citations, similar content": the kinds' labels, lowercase after the first. */
export const kindsText = (kinds: LinkKind[]): string =>
  kinds.map((kind, index) => (index === 0 ? KIND_LABELS[kind] : KIND_LABELS[kind].toLowerCase())).join(', ')

const pairKey = (a: string, b: string) => (a < b ? `${a} ${b}` : `${b} ${a}`)

/** The kinds joining each pair, whichever way round, in the controls' order. */
function pairKinds(links: GraphLink[]): Map<string, LinkKind[]> {
  const found = new Map<string, Set<LinkKind>>()
  for (const link of links) {
    const key = pairKey(link.source, link.target)
    found.set(key, new Set([...(found.get(key) ?? []), link.kind]))
  }
  return new Map([...found].map(([key, kinds]) => [key, KINDS.filter((kind) => kinds.has(kind))]))
}

/**
 * The Matrix (spec §5.3): the MATRIX_CAP most connected papers (visible links, then title), ordered by first
 * workspace (unfiled last), then link count, then title, so each project is a block on the diagonal. A cell with k
 * kinds of link wears the k-th colour of the sequential scale.
 */
export function matrix(nodes: GraphNode[], links: GraphLink[], theme: ChartTheme): Matrix {
  const degree = degrees(links)
  const count = (node: GraphNode) => degree.get(node.id) ?? 0
  const byTitle = (a: GraphNode, b: GraphNode) => a.title.localeCompare(b.title)
  const chosen = [...nodes].sort((a, b) => count(b) - count(a) || byTitle(a, b)).slice(0, MATRIX_CAP)
  const papers = chosen.sort((a, b) => byFirstWorkspace(a, b) || count(b) - count(a) || byTitle(a, b))
  const kindsOf = pairKinds(links)
  const scale = sequentialScale(theme)
  const cells = papers.map((row) =>
    papers.map((column) => {
      const kinds = row.id === column.id ? [] : (kindsOf.get(pairKey(row.id, column.id)) ?? [])
      if (kinds.length === 0) return null
      return { kinds, name: `${row.title} and ${column.title}: ${kindsText(kinds)}`, color: scale[kinds.length - 1][1] }
    })
  )
  return { papers, cells, capped: nodes.length > MATRIX_CAP }
}
