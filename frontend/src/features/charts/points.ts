import type { ResolvedCell, ResolvedData, ResolvedDataset } from '@/api/client'
import { datasetHref, regionHref } from '@/lib/route'
import type { PdfRect } from '../reader/coords'

/** Which cell a drawn point shows. Plotly carries it on each point as `customdata`. */
export type PointRef = { datasetId: string; rowId: string; columnId: string }

/** Where "Open source" goes: the spot on the paper's page, or the grid cell for data typed in (or whose paper is gone). */
export type PointSource =
  | { kind: 'paper'; paperId: string; page: number; rects: PdfRect[] }
  | { kind: 'dataset'; datasetId: string; rowId: string; columnId: string }

export const encodePoint = ({ datasetId, rowId, columnId }: PointRef): string => `${datasetId}|${rowId}|${columnId}`

export function decodePoint(value: unknown): PointRef | null {
  if (typeof value !== 'string') return null
  const [datasetId, rowId, columnId] = value.split('|')
  return datasetId && rowId && columnId ? { datasetId, rowId, columnId } : null
}

export function findCell(data: ResolvedData, ref: PointRef): { dataset: ResolvedDataset; cell: ResolvedCell } | null {
  const dataset = data.datasets.find((d) => d.id === ref.datasetId)
  const cell = dataset?.rows.find((r) => r.id === ref.rowId)?.cells[ref.columnId]
  return dataset && cell ? { dataset, cell } : null
}

/** The cell's own page and rects: a table's rows can sit on different lines, and a numbers dataset spans pages. */
export function pointSource(data: ResolvedData, ref: PointRef): PointSource | null {
  const found = findCell(data, ref)
  if (!found) return null
  const { dataset, cell } = found
  if (dataset.paper_id && cell.page !== null && cell.bbox && cell.bbox.length > 0) {
    return { kind: 'paper', paperId: dataset.paper_id, page: cell.page, rects: cell.bbox }
  }
  return { kind: 'dataset', ...ref }
}

export function sourceHref(source: PointSource): string {
  return source.kind === 'paper'
    ? regionHref(source.paperId, source.page, source.rects)
    : datasetHref(source.datasetId, { rowId: source.rowId, columnId: source.columnId })
}

/** "BERT · p. 6 · Table 2", "My data · runs.csv", "Source paper deleted · Table 2". */
export function sourceLabel(dataset: ResolvedDataset, cell?: ResolvedCell): string {
  if (dataset.kind === 'user') return `My data · ${dataset.name}`
  const page = cell?.page ?? dataset.page
  return [dataset.paper_title ?? 'Source paper deleted', page === null ? null : `p. ${page}`, dataset.name]
    .filter((part) => part !== null)
    .join(' · ')
}

/** A cell the owner changed after extraction read it. */
export const isEditedCell = (cell: ResolvedCell): boolean => cell.original_raw !== null && cell.original_raw !== cell.raw
