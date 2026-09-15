import type { ChartSpec, ResolvedData } from '@/api/client'
import { seriesName } from './compileSeries'
import { isEditedCell, sourceLabel } from './points'

/** A chart's numbers as a plain table: Plotly's SVG isn't screen-reader friendly, and some series colours are faint. */
export type ChartTableView = { columns: string[]; rows: string[][] }

const shown = (raw: string, edited: boolean) => (edited ? `${raw} (edited)` : raw)

export function chartTable(spec: ChartSpec, data: ResolvedData): ChartTableView {
  const byId = new Map(data.datasets.map((d) => [d.id, d]))
  if ('series' in spec) {
    const rows = spec.series.flatMap((series) => {
      const dataset = byId.get(series.dataset_id)
      if (!dataset || !dataset.columns.some((c) => c.id === series.y)) return []
      const chosen = series.rows ? new Set(series.rows) : null
      return dataset.rows
        .filter((row) => (chosen === null || chosen.has(row.id)) && row.cells[series.y])
        .map((row) => {
          const cell = row.cells[series.y]
          const x = series.x ? (row.cells[series.x]?.raw ?? '') : `Row ${row.position + 1}`
          return [seriesName(series, dataset), x, shown(cell.raw, isEditedCell(cell)), sourceLabel(dataset, cell)]
        })
    })
    return { columns: ['Series', 'Label', 'Value', 'Source'], rows }
  }
  const dataset = byId.get(spec.dataset_id)
  if (!dataset) return { columns: [], rows: [] }
  const ids =
    spec.type === 'heatmap'
      ? [spec.row_labels, ...spec.columns]
      : spec.type === 'parcoords'
        ? [...spec.dimensions, ...(spec.color_by ? [spec.color_by] : [])]
        : [spec.x, spec.y, spec.z]
  const columns = ids.flatMap((id) => dataset.columns.filter((c) => c.id === id))
  return {
    columns: columns.map((c) => c.name),
    rows: dataset.rows.map((row) => columns.map((c) => (row.cells[c.id] ? shown(row.cells[c.id].raw, isEditedCell(row.cells[c.id])) : ''))),
  }
}
