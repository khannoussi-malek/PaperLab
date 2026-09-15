import type { Data, Layout } from 'plotly.js-dist-min'
import type { ResolvedCell, ResolvedData, ResolvedDataset, SeriesChartSpec, SeriesSpec } from '@/api/client'
import { escapeText, fitLinear, symlog, symlogTicks } from './chartMath'
import { axisStyle, baseLayout, CHART_INK, seriesColor, type ChartTheme } from './palette'
import { encodePoint, isEditedCell, sourceLabel } from './points'

export type Compiled = {
  traces: Data[]
  layout: Partial<Layout>
  /** Shown above the chart, e.g. "1 series lost its data". */
  warnings: string[]
  /** Series actually drawn: what the builder's preview and the E2E specs count. */
  seriesCount: number
}

/** One drawn point, before any scale transform. */
type Point = {
  xLabel: string
  x: number | null
  y: number | null
  error: number | null
  z: number | null
  ref: string
  hover: string
}

type LiveSeries = { series: SeriesSpec; dataset: ResolvedDataset; points: Point[]; name: string }

const format = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 })
const hasColumn = (dataset: ResolvedDataset, id: string | null | undefined) =>
  id === null || id === undefined || dataset.columns.some((c) => c.id === id)
const columnName = (dataset: ResolvedDataset, id: string | null | undefined) => {
  const column = dataset.columns.find((c) => c.id === id)
  return column ? (column.unit ? `${column.name} (${column.unit})` : column.name) : ''
}

/** The legend's name: the series' own, else its y column; a multiplier is always visible. */
export function seriesName(series: SeriesSpec, dataset: ResolvedDataset): string {
  const name = series.name.trim() || columnName(dataset, series.y) || 'Series'
  return series.multiply === 1 ? name : `${name} ×${format.format(series.multiply)}`
}

/** A missing dataset or any column the series names makes the whole series lost; the rest still draw. */
function isDrawable(series: SeriesSpec, dataset: ResolvedDataset | undefined): dataset is ResolvedDataset {
  if (!dataset) return false
  const error = series.error === 'none' || series.error === 'cells' ? null : series.error
  return [series.x, series.y, series.z, error].every((id) => hasColumn(dataset, id))
}

function hoverText(cell: ResolvedCell, name: string, xLabel: string, dataset: ResolvedDataset): string {
  // Values lead; names come from PDFs, CSV headers and typing, so every text is escaped for Plotly's HTML subset.
  const value = `<b>${escapeText(cell.raw)}</b>${isEditedCell(cell) ? ' · edited' : ''}`
  const what = [name, xLabel].filter(Boolean).map(escapeText).join(' · ')
  return `${value}<br>${what}<br>${escapeText(sourceLabel(dataset, cell))}`
}

function points(series: SeriesSpec, dataset: ResolvedDataset, name: string): Point[] {
  const chosen = series.rows ? new Set(series.rows) : null
  return dataset.rows
    .filter((row) => chosen === null || chosen.has(row.id))
    .flatMap((row) => {
      const cell = row.cells[series.y]
      if (!cell) return []
      const xCell = series.x ? row.cells[series.x] : undefined
      const xLabel = xCell ? xCell.raw : `Row ${row.position + 1}`
      const errorCell = series.error === 'none' || series.error === 'cells' ? undefined : row.cells[series.error]
      const error = series.error === 'cells' ? cell.error : (errorCell?.value ?? null)
      const scaled = (value: number | null) => (value === null ? null : value * series.multiply)
      return [
        {
          xLabel,
          x: xCell ? xCell.value : row.position + 1,
          y: scaled(cell.value),
          error: error === null ? null : Math.abs(error * series.multiply),
          z: series.z ? (row.cells[series.z]?.value ?? null) : null,
          ref: encodePoint({ datasetId: dataset.id, rowId: row.id, columnId: series.y }),
          hover: hoverText(cell, name, xCell ? xCell.raw : '', dataset),
        },
      ]
    })
}

/** Bars and boxes always read x as categories; so does an x column with no numbers in it. */
function categoricalX(spec: SeriesChartSpec, live: LiveSeries[]): boolean {
  if (spec.type === 'bar' || spec.type === 'box' || spec.axes?.x?.scale === 'category') return true
  return live.every((s) => s.series.x !== null && s.series.x !== undefined && s.points.every((p) => p.x === null))
}

const transform = (scale: string | undefined) => (value: number | null) =>
  value === null ? null : scale === 'symlog' ? symlog(value) : value

function errorBars(points: Point[], scale: string | undefined) {
  if (points.every((p) => p.error === null)) return {}
  if (scale !== 'symlog') {
    return { error_y: { type: 'data', array: points.map((p) => p.error ?? 0), visible: true, thickness: 1.5, width: 4 } }
  }
  // On a symlog axis the bar's ends are transformed, so the error bar is uneven.
  const up = points.map((p) => (p.y === null || p.error === null ? 0 : symlog(p.y + p.error) - symlog(p.y)))
  const down = points.map((p) => (p.y === null || p.error === null ? 0 : symlog(p.y) - symlog(p.y - p.error)))
  return { error_y: { type: 'data', symmetric: false, array: up, arrayminus: down, visible: true, thickness: 1.5, width: 4 } }
}

/** A straight segment in data space: callers only draw it when both axes are linear, where it is still straight. */
function trendTrace(live: LiveSeries, color: string, xCategorical: boolean, axes: object): Data[] {
  const pairs = live.points
    .map((p, i) => ({ x: xCategorical ? i + 1 : p.x, y: p.y, label: p.xLabel }))
    .filter((p): p is { x: number; y: number; label: string } => p.x !== null && p.y !== null)
  const fit = fitLinear(
    pairs.map((p) => p.x),
    pairs.map((p) => p.y),
  )
  if (!fit) return []
  const ends = xCategorical ? pairs : [...pairs].sort((a, b) => a.x - b.x).filter((_, i, all) => i === 0 || i === all.length - 1)
  return [
    {
      type: 'scatter',
      mode: 'lines',
      name: `${escapeText(live.name)} · linear trend (R² ${fit.r2.toFixed(2)})`,
      x: ends.map((p) => (xCategorical ? escapeText(p.label) : p.x)),
      y: ends.map((p) => fit.slope * p.x + fit.intercept),
      line: { color, width: 2, dash: 'dash' },
      hoverinfo: 'skip',
      ...axes,
    } as Data,
  ]
}

function trace(spec: SeriesChartSpec, live: LiveSeries, color: string, xCategorical: boolean, theme: ChartTheme, axes: object): Data {
  const xScale = spec.axes?.x?.scale
  const yScale = spec.axes?.y?.scale
  // Category labels are cell text, drawn as tick labels: escaped like every other text.
  const x = live.points.map((p) => (xCategorical ? escapeText(p.xLabel) : transform(xScale)(p.x)))
  const y = live.points.map((p) => transform(yScale)(p.y))
  const common = {
    name: escapeText(live.name),
    customdata: live.points.map((p) => p.ref),
    hovertext: live.points.map((p) => p.hover),
    hovertemplate: '%{hovertext}<extra></extra>',
    ...axes,
  }
  const ring = { color: CHART_INK[theme].surface, width: 2 }
  switch (spec.type) {
    case 'bar':
      return { type: 'bar', x, y, marker: { color, line: { width: 0 } }, textposition: 'none', ...errorBars(live.points, yScale), ...common } as Data
    case 'line':
      return {
        type: 'scatter',
        mode: 'lines+markers',
        x,
        y,
        line: { color, width: 2 },
        marker: { color, size: 8, line: ring },
        ...errorBars(live.points, yScale),
        ...common,
      } as Data
    case 'scatter':
      return { type: 'scatter', mode: 'markers', x, y, marker: { color, size: 9, line: ring }, ...errorBars(live.points, yScale), ...common } as Data
    case 'box':
      return {
        type: 'box',
        x: live.series.x ? x : undefined,
        y,
        marker: { color, size: 6 },
        line: { color, width: 1.5 },
        boxpoints: 'all',
        jitter: 0.3,
        pointpos: 0,
        ...common,
      } as Data
    case 'scatter3d':
      return {
        type: 'scatter3d',
        mode: 'markers',
        x: live.points.map((p) => p.x),
        y: live.points.map((p) => p.y),
        z: live.points.map((p) => p.z),
        marker: { color, size: 5 },
        ...common,
      } as Data
  }
}

function axisType(scale: string | undefined, categorical: boolean): 'category' | 'log' | 'linear' {
  if (categorical) return 'category'
  return scale === 'log' ? 'log' : 'linear'
}

/** Axis settings for one panel: type, title and, for symlog, ticks labelled in the values a reader knows. */
function axis(theme: ChartTheme, title: string, scale: string | undefined, categorical: boolean, values: (number | null)[]) {
  const numbers = values.filter((v): v is number => v !== null)
  const ticks = scale === 'symlog' && !categorical && numbers.length > 0 ? symlogTicks(Math.min(...numbers), Math.max(...numbers)) : {}
  return { ...axisStyle(theme), type: axisType(scale, categorical), title: { text: escapeText(title) }, ...ticks }
}

export function compileSeriesChart(spec: SeriesChartSpec, data: ResolvedData, theme: ChartTheme): Compiled {
  const byId = new Map(data.datasets.map((d) => [d.id, d]))
  const live: LiveSeries[] = spec.series.flatMap((series) => {
    const dataset = byId.get(series.dataset_id)
    if (!isDrawable(series, dataset)) return []
    const name = seriesName(series, dataset)
    return [{ series, dataset, points: points(series, dataset, name), name }]
  })
  const lost = spec.series.length - live.length
  const warnings = lost > 0 ? [`${lost} series lost ${lost === 1 ? 'its' : 'their'} data`] : []
  const layout: Partial<Layout> = { ...baseLayout(theme) }
  if (live.length === 0) return { traces: [], layout, warnings, seriesCount: 0 }

  const xCategorical = categoricalX(spec, live)
  const first = live[0]
  const xTitle = spec.axes?.x?.label || (first.series.x ? columnName(first.dataset, first.series.x) : '')
  const yTitle = spec.axes?.y?.label || columnName(first.dataset, first.series.y)
  const facet = spec.layout?.facet === 'series' && spec.type !== 'scatter3d'
  const linearAxes = ![spec.axes?.x?.scale, spec.axes?.y?.scale].some((scale) => scale === 'log' || scale === 'symlog')
  const trendRefused = !linearAxes && live.some((s) => s.series.trend === 'linear')
  const traces: Data[] = []

  live.forEach((s, i) => {
    // Small multiples name each panel, so every panel uses the first colour instead of cycling through the palette.
    const color = seriesColor(theme, facet ? 0 : i, s.series.color)
    const axes = facet && i > 0 ? { xaxis: `x${i + 1}`, yaxis: `y${i + 1}` } : {}
    traces.push(trace(spec, s, color, xCategorical, theme, axes))
    if (s.series.trend === 'linear' && linearAxes) traces.push(...trendTrace(s, color, xCategorical, axes))
  })

  const xValues = live.flatMap((s) => s.points.map((p) => p.x))
  const yValues = live.flatMap((s) => s.points.map((p) => p.y))
  const xAxis = axis(theme, xTitle, spec.axes?.x?.scale, xCategorical, xValues)
  const yAxis = axis(theme, yTitle, spec.axes?.y?.scale, false, yValues)

  if (spec.type === 'scatter3d') {
    const zTitle = spec.axes?.z?.label || columnName(first.dataset, first.series.z)
    const zValues = live.flatMap((s) => s.points.map((p) => p.z))
    layout.scene = { xaxis: xAxis, yaxis: yAxis, zaxis: axis(theme, zTitle, spec.axes?.z?.scale, false, zValues) }
  } else if (facet) {
    const columns = Math.min(spec.layout?.facet_columns ?? 2, live.length)
    layout.grid = { rows: Math.ceil(live.length / columns), columns, pattern: 'independent' }
    const panels = layout as Record<string, unknown>
    live.forEach((_, i) => {
      const suffix = i === 0 ? '' : String(i + 1)
      panels[`xaxis${suffix}`] = xAxis
      panels[`yaxis${suffix}`] = { ...yAxis, title: { text: '' } }
    })
    layout.annotations = live.map((s, i) => ({
      text: escapeText(s.name),
      xref: `x${i === 0 ? '' : i + 1} domain`,
      yref: `y${i === 0 ? '' : i + 1} domain`,
      x: 0,
      y: 1.12,
      xanchor: 'left',
      showarrow: false,
      font: { color: CHART_INK[theme].text },
    })) as Layout['annotations']
  } else {
    layout.xaxis = xAxis
    layout.yaxis = yAxis
  }
  if (spec.type === 'bar') layout.barmode = spec.layout?.barmode ?? 'group'
  // A legend for two or more entries; one series is named by the chart's title, and small multiples by their panels.
  layout.showlegend = !facet && traces.length >= 2
  const allWarnings = trendRefused ? [...warnings, 'Trend lines are drawn on linear axes only'] : warnings
  return { traces, layout, warnings: allWarnings, seriesCount: live.length }
}
