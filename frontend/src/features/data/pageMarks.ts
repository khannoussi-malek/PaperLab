import type { Dataset, DatasetSummary } from '@/api/client'
import type { PdfRect } from '../reader/coords'
import { rectContains } from '../reader/hitTest'

/** The ▦ marker's size in PDF points, at the top-right corner inside a captured table's region. */
export const MARKER_PT = 14
/** A dragged box smaller than this (in points) on either side is a click, not a table. */
export const MIN_REGION_PT = 10

export type TableMark = { datasetId: string; name: string; region: PdfRect; marker: PdfRect }
export type NumberMark = { rowId: string; rects: PdfRect[] }

const push = <T>(map: Map<number, T[]>, page: number, item: T) => map.set(page, [...(map.get(page) ?? []), item])

/** Captured tables by page: the region's outline and its marker. */
export function tableMarks(datasets: DatasetSummary[]): Map<number, TableMark[]> {
  const marks = new Map<number, TableMark[]>()
  for (const d of datasets) {
    if (d.kind !== 'table' || d.page === null || d.region === null) continue
    const [, y0, x1] = d.region
    push(marks, d.page, { datasetId: d.id, name: d.name, region: d.region, marker: [x1 - MARKER_PT, y0, x1, y0 + MARKER_PT] })
  }
  return marks
}

/** Numbers picked from the text, by page: each row's anchored cell rects, for the dashed underline. */
export function numberMarks(numbers: Dataset | null | undefined): Map<number, NumberMark[]> {
  const marks = new Map<number, NumberMark[]>()
  for (const row of numbers?.rows ?? []) {
    const anchored = row.cells.find((c) => c.page !== null && c.bbox !== null && c.bbox.length > 0)
    if (anchored) push(marks, anchored.page!, { rowId: row.id, rects: anchored.bbox! })
  }
  return marks
}

/** The table whose marker is under the point, if any. */
export const tableMarkerAt = (marks: TableMark[], point: [number, number]): TableMark | null =>
  marks.find((m) => rectContains(m.marker, point)) ?? null

/** The box dragged between two points on a page, in PDF points and kept on the page; null for a click-sized drag. */
export function dragRegion(start: [number, number], end: [number, number], page: { width: number; height: number }): PdfRect | null {
  const clamp = (value: number, max: number) => Math.round(Math.min(Math.max(value, 0), max) * 100) / 100
  const [x0, x1] = [clamp(Math.min(start[0], end[0]), page.width), clamp(Math.max(start[0], end[0]), page.width)]
  const [y0, y1] = [clamp(Math.min(start[1], end[1]), page.height), clamp(Math.max(start[1], end[1]), page.height)]
  return x1 - x0 < MIN_REGION_PT || y1 - y0 < MIN_REGION_PT ? null : [x0, y0, x1, y1]
}
