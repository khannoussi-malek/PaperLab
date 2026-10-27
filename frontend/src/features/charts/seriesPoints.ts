import type { ResolvedCell, ResolvedDataset, SeriesSpec } from '@/api/client'

const format = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 })
const hasColumn = (dataset: ResolvedDataset, id: string | null | undefined) =>
  id === null || id === undefined || dataset.columns.some((c) => c.id === id)
export const columnName = (dataset: ResolvedDataset, id: string | null | undefined) => {
  const column = dataset.columns.find((c) => c.id === id)
  return column ? (column.unit ? `${column.name} (${column.unit})` : column.name) : ''
}

/** The legend's name: the series' own, else its y column; a multiplier is always visible. */
export function seriesName(series: SeriesSpec, dataset: ResolvedDataset): string {
  const name = series.name.trim() || columnName(dataset, series.y) || 'Series'
  return series.multiply === 1 ? name : `${name} ×${format.format(series.multiply)}`
}

/** A missing dataset or any column the series names makes the whole series lost; the rest still draw. */
export function isDrawable(series: SeriesSpec, dataset: ResolvedDataset | undefined): dataset is ResolvedDataset {
  if (!dataset) return false
  const error = series.error === 'none' || series.error === 'cells' ? null : series.error
  return [series.x, series.y, series.z, error].every((id) => hasColumn(dataset, id))
}

/** One point of a series, before any scale transform or plot library: filters, multiply, x and error all applied. */
export type SeriesPoint = {
  xLabel: string
  xRaw: string
  x: number | null
  y: number | null
  error: number | null
  z: number | null
  rowId: string
  cell: ResolvedCell
}

export function seriesPoints(series: SeriesSpec, dataset: ResolvedDataset): SeriesPoint[] {
  const chosen = series.rows ? new Set(series.rows) : null
  return dataset.rows
    .filter((row) => chosen === null || chosen.has(row.id))
    .flatMap((row) => {
      const cell = row.cells[series.y]
      if (!cell) return []
      const xCell = series.x ? row.cells[series.x] : undefined
      const errorCell = series.error === 'none' || series.error === 'cells' ? undefined : row.cells[series.error]
      const error = series.error === 'cells' ? cell.error : (errorCell?.value ?? null)
      const scaled = (value: number | null) => (value === null ? null : value * series.multiply)
      return [
        {
          xLabel: xCell ? xCell.raw : `Row ${row.position + 1}`,
          xRaw: xCell ? xCell.raw : '',
          x: xCell ? xCell.value : row.position + 1,
          y: scaled(cell.value),
          error: error === null ? null : Math.abs(error * series.multiply),
          z: series.z ? (row.cells[series.z]?.value ?? null) : null,
          rowId: row.id,
          cell,
        },
      ]
    })
}
