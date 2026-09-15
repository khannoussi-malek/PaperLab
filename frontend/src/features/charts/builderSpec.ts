import type { ChartSpec, Dataset, SeriesChartSpec, SeriesSpec } from '@/api/client'

export type ChartType = ChartSpec['type']
type SeriesType = SeriesChartSpec['type']

/** The builder's type picker, in its three groups. */
export const TYPE_GROUPS: { label: string; types: { type: ChartType; name: string }[] }[] = [
  { label: 'Compare values', types: [{ type: 'bar', name: 'Bar' }, { type: 'line', name: 'Line' }, { type: 'scatter', name: 'Scatter' }] },
  { label: 'Distributions', types: [{ type: 'box', name: 'Box' }, { type: 'heatmap', name: 'Heatmap' }] },
  {
    label: 'Many dimensions',
    types: [
      { type: 'scatter3d', name: '3D scatter' },
      { type: 'surface', name: 'Surface' },
      { type: 'contour', name: 'Contour' },
      { type: 'parcoords', name: 'Parallel' },
    ],
  },
]

/** How many series one panel can hold before they must be split into small multiples (the server checks the same). */
export const PANEL_LIMIT: Record<SeriesType, number> = { bar: 6, line: 6, box: 6, scatter: 3, scatter3d: 3 }

export const isSeriesType = (type: ChartType): type is SeriesType =>
  type === 'bar' || type === 'line' || type === 'scatter' || type === 'box' || type === 'scatter3d'

export type ColumnInfo = { id: string; name: string; numeric: boolean; hasErrors: boolean; samples: string[] }

/** Each column with whether it holds numbers (any parsed value) and its first few texts, for the column pickers. */
export function columnInfo(dataset: Dataset): ColumnInfo[] {
  return dataset.columns.map((column) => {
    const cells = dataset.rows.map((row) => row.cells.find((c) => c.column_id === column.id)).filter((c) => c !== undefined)
    return {
      id: column.id,
      name: column.name,
      numeric: cells.some((c) => c.value !== null),
      hasErrors: cells.some((c) => c.error !== null),
      samples: cells.map((c) => c.raw).filter(Boolean).slice(0, 3),
    }
  })
}

export const nextSeriesId = (series: SeriesSpec[]): string => {
  const taken = new Set(series.map((s) => s.id))
  let n = series.length + 1
  while (taken.has(`s${n}`)) n += 1
  return `s${n}`
}

/** A new series from a dataset: its first text column on x, its first number column (not already charted) on y. */
export function newSeries(dataset: Dataset, existing: SeriesSpec[]): SeriesSpec | null {
  const info = columnInfo(dataset)
  const used = new Set(existing.filter((s) => s.dataset_id === dataset.id).map((s) => s.y))
  const numbers = info.filter((c) => c.numeric)
  const y = numbers.find((c) => !used.has(c.id)) ?? numbers[0]
  if (!y) return null
  return {
    id: nextSeriesId(existing),
    name: '',
    dataset_id: dataset.id,
    x: info.find((c) => !c.numeric)?.id ?? null,
    y: y.id,
    error: y.hasErrors ? 'cells' : 'none',
    trend: 'none',
    multiply: 1,
  }
}

/** "Quick chart" from the Data tab: a bar of every number column against the first text column. */
export function quickChartSpec(dataset: Dataset): SeriesChartSpec | null {
  const info = columnInfo(dataset)
  const x = info.find((c) => !c.numeric)?.id ?? null
  const series: SeriesSpec[] = info
    .filter((c) => c.numeric)
    .map((c, i) => ({
      id: `s${i + 1}`,
      name: '',
      dataset_id: dataset.id,
      x,
      y: c.id,
      error: c.hasErrors ? 'cells' : 'none',
      trend: 'none',
      multiply: 1,
    }))
  if (series.length === 0) return null
  const facet = series.length > PANEL_LIMIT.bar ? 'series' : 'none'
  return { version: 1, type: 'bar', series: series.slice(0, 20), layout: { barmode: 'group', facet, facet_columns: 2 } }
}

/**
 * Switches type, keeping what still makes sense: series stay series (dropping z and trend lines where they can't
 * be drawn), and a grid chart takes its columns from the first series' dataset. Moving back from a grid chart starts
 * again from `dataset`.
 */
export function changeType(spec: ChartSpec | null, type: ChartType, dataset: Dataset | null): ChartSpec | null {
  const base = { version: 1 as const, axes: spec?.axes, layout: spec?.layout }
  const series = spec && 'series' in spec ? spec.series : []
  const first = series[0]
  const columns = dataset ? columnInfo(dataset) : []
  const numeric = columns.filter((c) => c.numeric).map((c) => c.id)
  const text = columns.find((c) => !c.numeric)?.id ?? null

  if (isSeriesType(type)) {
    const kept = series.length > 0 ? series : dataset ? (quickChartSpec(dataset)?.series ?? []) : []
    if (kept.length === 0) return null
    const drawable = kept.map((s) => ({
      ...s,
      z: type === 'scatter3d' ? (s.z ?? numeric.find((id) => id !== s.y) ?? null) : null,
      x: type === 'scatter3d' ? (s.x && numeric.includes(s.x) ? s.x : (numeric.find((id) => id !== s.y) ?? null)) : s.x,
      trend: type === 'line' || type === 'scatter' ? s.trend : ('none' as const),
    }))
    const facet = drawable.length > PANEL_LIMIT[type] && type !== 'scatter3d' ? 'series' : (spec?.layout?.facet ?? 'none')
    return { ...base, type, series: drawable, layout: { barmode: 'group', facet_columns: 2, ...spec?.layout, facet } }
  }

  const datasetId = first?.dataset_id ?? dataset?.id
  if (!datasetId) return null
  const ys = first ? series.filter((s) => s.dataset_id === datasetId).map((s) => s.y) : numeric
  if (type === 'heatmap') {
    const rowLabels = first?.x ?? text ?? columns[0]?.id
    return rowLabels && ys.length > 0 ? { ...base, type, dataset_id: datasetId, row_labels: rowLabels, columns: ys } : null
  }
  if (type === 'parcoords') {
    return ys.length >= 2 ? { ...base, type, dataset_id: datasetId, dimensions: ys, color_by: null } : null
  }
  const [x, y, z] = first && first.x && first.z ? [first.x, first.y, first.z] : numeric
  return x && y && z ? { ...base, type, dataset_id: datasetId, x, y, z } : null
}

const TYPE_NAMES = Object.fromEntries(TYPE_GROUPS.flatMap((g) => g.types.map((t) => [t.type, t.name])))

/**
 * Why the builder can't save this spec yet, in words, or null. The server refuses the same specs, but a refused
 * spec comes back as a validation list the UI can only summarise, so the builder says it first.
 */
export function panelProblem(spec: ChartSpec | null): string | null {
  if (!spec) return 'Add a series to start the chart.'
  if (!('series' in spec)) return null
  if (spec.series.length > 20) return 'A chart holds at most 20 series.'
  const limit = PANEL_LIMIT[spec.type]
  if (spec.layout?.facet !== 'series' && spec.series.length > limit) {
    const panels = spec.type === 'scatter3d' ? 'Remove a series.' : 'Turn on small multiples, or remove a series.'
    return `${TYPE_NAMES[spec.type]} charts show at most ${limit} series in one panel. ${panels}`
  }
  return null
}

/** Every dataset the spec reads: what the builder loads to fill its pickers. */
export function specDatasetIds(spec: ChartSpec | null): string[] {
  if (!spec) return []
  return 'series' in spec ? [...new Set(spec.series.map((s) => s.dataset_id))] : [spec.dataset_id]
}
