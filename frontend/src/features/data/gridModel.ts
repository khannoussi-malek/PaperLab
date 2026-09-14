import type { ChartUse, Dataset, GridIn, TablePreview } from '@/api/client'
import type { PdfRect } from '../reader/coords'

/**
 * The grid the owner fixes before saving a table, or edits later. Pure and immutable: every operation returns a new
 * grid. `extracted` is what extraction read from the PDF (null for a typed cell); the server marks a cell "edited" when
 * `raw` differs from it. Rows and columns keep their server `id` (null until saved) so charts keep pointing at them;
 * `key` is only for React.
 */
export type GridCell = { raw: string; extracted: string | null; page: number | null; bbox: PdfRect[] | null }
export type GridColumn = { key: string; id: string | null; name: string; unit: string | null }
export type GridRow = { key: string; id: string | null; cells: GridCell[] }
export type Grid = { columns: GridColumn[]; rows: GridRow[] }

const EMPTY: GridCell = { raw: '', extracted: null, page: null, bbox: null }

let created = 0
const newKey = () => `new-${++created}`

const replaceAt = <T>(items: T[], index: number, item: T): T[] => items.map((existing, i) => (i === index ? item : existing))
const insertAt = <T>(items: T[], index: number, item: T): T[] => [...items.slice(0, index), item, ...items.slice(index)]
const removeAt = <T>(items: T[], index: number): T[] => items.filter((_, i) => i !== index)

export function fromPreview(preview: TablePreview): Grid {
  return {
    columns: preview.grid.columns.map((c, i) => ({ key: `c${i}`, id: c.id ?? null, name: c.name, unit: c.unit ?? null })),
    rows: preview.grid.rows.map((row, i) => ({
      key: `r${i}`,
      id: row.id ?? null,
      cells: row.cells.map((c) => ({ raw: c.raw, extracted: c.extracted ?? null, page: c.page ?? null, bbox: c.bbox ?? null })),
    })),
  }
}

export function fromDataset(dataset: Dataset): Grid {
  return {
    columns: dataset.columns.map((c) => ({ key: c.id, id: c.id, name: c.name, unit: c.unit })),
    rows: dataset.rows.map((row) => ({
      key: row.id,
      id: row.id,
      cells: row.cells.map((c) => ({
        raw: c.raw,
        // An edited cell's server copy keeps what extraction read in `original_raw`.
        extracted: c.origin === 'extracted' ? (c.original_raw ?? c.raw) : null,
        page: c.page,
        bbox: c.bbox,
      })),
    })),
  }
}

export function toGridIn(grid: Grid): GridIn {
  return {
    columns: grid.columns.map(({ id, name, unit }) => ({ id, name, unit })),
    rows: grid.rows.map(({ id, cells }) => ({ id, cells: cells.map(({ raw, extracted, page, bbox }) => ({ raw, extracted, page, bbox })) })),
  }
}

export const isEdited = (cell: GridCell): boolean => cell.extracted !== null && cell.raw !== cell.extracted

export function emptyGrid(names: string[], rowCount: number): Grid {
  return {
    columns: names.map((name) => ({ key: newKey(), id: null, name, unit: null })),
    rows: Array.from({ length: rowCount }, () => ({ key: newKey(), id: null, cells: names.map(() => EMPTY) })),
  }
}

const mapRows = (grid: Grid, change: (row: GridRow, index: number) => GridRow): Grid => ({ ...grid, rows: grid.rows.map(change) })

export function editCell(grid: Grid, row: number, column: number, raw: string): Grid {
  return mapRows(grid, (r, i) => (i === row ? { ...r, cells: replaceAt(r.cells, column, { ...r.cells[column], raw }) } : r))
}

export function renameColumn(grid: Grid, column: number, name: string): Grid {
  return { ...grid, columns: replaceAt(grid.columns, column, { ...grid.columns[column], name }) }
}

export function setUnit(grid: Grid, column: number, unit: string | null): Grid {
  return { ...grid, columns: replaceAt(grid.columns, column, { ...grid.columns[column], unit }) }
}

/** The row's texts become (or extend, joined with " / ") the column names, and the row is removed. */
export function useRowAsHeader(grid: Grid, row: number): Grid {
  const cells = grid.rows[row].cells
  return {
    columns: grid.columns.map((c, i) => ({ ...c, name: [c.name, cells[i].raw.trim()].filter(Boolean).join(' / ') })),
    rows: removeAt(grid.rows, row),
  }
}

function joinCells(left: GridCell, right: GridCell): GridCell {
  if (!right.raw.trim()) return left
  if (!left.raw.trim()) return right
  // Only text extraction actually read counts as extracted, so typed text joined in shows as an edit.
  const read = [left.extracted, right.extracted].filter((text): text is string => text !== null)
  return {
    raw: `${left.raw.trim()} ${right.raw.trim()}`,
    extracted: read.length > 0 ? read.join(' ') : null,
    page: left.page ?? right.page,
    bbox: left.bbox || right.bbox ? [...(left.bbox ?? []), ...(right.bbox ?? [])] : null,
  }
}

/** Joins the column right of `left` into it. The left column keeps its id; the right one is removed. */
export function mergeColumns(grid: Grid, left: number): Grid {
  if (left < 0 || left >= grid.columns.length - 1) return grid
  const [a, b] = [grid.columns[left], grid.columns[left + 1]]
  const merged = { ...a, name: [a.name, b.name].filter(Boolean).join(' '), unit: a.unit ?? b.unit }
  return {
    columns: removeAt(replaceAt(grid.columns, left, merged), left + 1),
    rows: grid.rows.map((row) => ({
      ...row,
      cells: removeAt(replaceAt(row.cells, left, joinCells(row.cells[left], row.cells[left + 1])), left + 1),
    })),
  }
}

const words = (text: string) => text.trim().split(/\s+/).filter(Boolean)

/**
 * Keeps each cell's first `keep` words and moves the rest into a new column on the right.
 * ponytail: both halves keep the cell's whole page rect, since a cell doesn't store each word's box; "Show in paper"
 * then highlights the original cell. Store word boxes if that ever matters.
 */
export function splitColumn(grid: Grid, column: number, keep: number): Grid {
  if (!grid.rows.some((row) => words(row.cells[column].raw).length > keep)) return grid
  const split = (cell: GridCell): [GridCell, GridCell] => {
    const parts = words(cell.raw)
    if (parts.length <= keep) return [cell, EMPTY]
    const read = cell.extracted === null ? null : words(cell.extracted)
    const half = (from: number, to?: number): GridCell => ({
      raw: parts.slice(from, to).join(' '),
      extracted: read === null ? null : read.slice(from, to).join(' '),
      page: cell.page,
      bbox: cell.bbox,
    })
    return [half(0, keep), half(keep)]
  }
  return {
    columns: insertAt(grid.columns, column + 1, { key: newKey(), id: null, name: '', unit: null }),
    rows: grid.rows.map((row) => {
      const [left, right] = split(row.cells[column])
      return { ...row, cells: insertAt(replaceAt(row.cells, column, left), column + 1, right) }
    }),
  }
}

/** Empty cells take the text above them, as typed values: grouped labels like "(A)" printed once per group. */
export function fillDown(grid: Grid, column: number): Grid {
  let above: string | null = null
  return mapRows(grid, (row) => {
    const cell = row.cells[column]
    if (cell.raw.trim()) {
      above = cell.raw
      return row
    }
    return above === null ? row : { ...row, cells: replaceAt(row.cells, column, { ...EMPTY, raw: above }) }
  })
}

export function insertRow(grid: Grid, index: number): Grid {
  return { ...grid, rows: insertAt(grid.rows, index, { key: newKey(), id: null, cells: grid.columns.map(() => EMPTY) }) }
}

export const deleteRow = (grid: Grid, index: number): Grid => ({ ...grid, rows: removeAt(grid.rows, index) })

export function insertColumn(grid: Grid, index: number): Grid {
  return {
    columns: insertAt(grid.columns, index, { key: newKey(), id: null, name: '', unit: null }),
    rows: grid.rows.map((row) => ({ ...row, cells: insertAt(row.cells, index, EMPTY) })),
  }
}

export function deleteColumn(grid: Grid, index: number): Grid {
  return { columns: removeAt(grid.columns, index), rows: grid.rows.map((row) => ({ ...row, cells: removeAt(row.cells, index) })) }
}

/** Charts that name a column this grid no longer has: saving it needs the owner's go-ahead (the API answers 409). */
export function chartsLosingColumns(charts: ChartUse[], grid: Grid): ChartUse[] {
  const kept = new Set(grid.columns.map((c) => c.id))
  return charts.filter((chart) => chart.column_ids.some((id) => !kept.has(id)))
}
