import type { Data, Layout } from 'plotly.js-dist-min'
import type { ChartSpec, ResolvedData, ResolvedDataset } from '@/api/client'
import { escapeText } from './chartMath'
import type { Compiled } from './compileSeries'
import { axisStyle, baseLayout, CHART_INK, sequentialScale, seriesColor, type ChartTheme } from './palette'
import { encodePoint, isEditedCell, sourceLabel } from './points'

type GridSpec = Exclude<ChartSpec, { type: 'bar' | 'line' | 'scatter' | 'box' | 'scatter3d' }>

const GONE = "This chart's data is gone"

const counted = (count: number, word: string) =>
  `${count} ${word}${count === 1 ? '' : 's'} lost ${count === 1 ? 'its' : 'their'} data`

function cellHover(dataset: ResolvedDataset, rowId: string, columnId: string, what: string[]): string {
  const cell = dataset.rows.find((r) => r.id === rowId)?.cells[columnId]
  if (!cell) return ''
  const value = `<b>${escapeText(cell.raw)}</b>${isEditedCell(cell) ? ' · edited' : ''}`
  return `${value}<br>${what.filter(Boolean).map(escapeText).join(' · ')}<br>${escapeText(sourceLabel(dataset, cell))}`
}

const title = (text: string) => ({ text: escapeText(text) })
const nameOf = (dataset: ResolvedDataset, id: string | null | undefined) => dataset.columns.find((c) => c.id === id)?.name ?? ''

function heatmap(spec: Extract<GridSpec, { type: 'heatmap' }>, dataset: ResolvedDataset, theme: ChartTheme): Compiled {
  const columns = spec.columns.flatMap((id) => dataset.columns.filter((c) => c.id === id))
  const lost = spec.columns.length - columns.length
  const labels = dataset.rows.map((row) => row.cells[spec.row_labels]?.raw || `Row ${row.position + 1}`)
  const trace: Data = {
    type: 'heatmap',
    x: columns.map((c) => escapeText(c.name)),
    y: labels.map(escapeText),
    z: dataset.rows.map((row) => columns.map((c) => row.cells[c.id]?.value ?? null)),
    customdata: dataset.rows.map((row) => columns.map((c) => encodePoint({ datasetId: dataset.id, rowId: row.id, columnId: c.id }))),
    hovertext: dataset.rows.map((row, r) => columns.map((c) => cellHover(dataset, row.id, c.id, [labels[r], c.name]))),
    hovertemplate: '%{hovertext}<extra></extra>',
    colorscale: sequentialScale(theme),
    // The surface gap between cells.
    xgap: 2,
    ygap: 2,
  } as Data
  const layout: Partial<Layout> = {
    ...baseLayout(theme),
    xaxis: { ...axisStyle(theme), type: 'category', title: title(spec.axes?.x?.label ?? '') },
    yaxis: { ...axisStyle(theme), type: 'category', autorange: 'reversed' as const, title: title(spec.axes?.y?.label || nameOf(dataset, spec.row_labels)) },
  }
  return { traces: [trace], layout, warnings: lost > 0 ? [counted(lost, 'column')] : [], seriesCount: 1 }
}

/** Long format (one row per x, y point) pivoted into the grid a surface or contour needs. */
function surface(spec: Extract<GridSpec, { type: 'surface' | 'contour' }>, dataset: ResolvedDataset, theme: ChartTheme): Compiled {
  const rows = dataset.rows.flatMap((row) => {
    const [x, y, z] = [row.cells[spec.x]?.value, row.cells[spec.y]?.value, row.cells[spec.z]?.value]
    return x === null || x === undefined || y === null || y === undefined || z === undefined ? [] : [{ row, x, y, z }]
  })
  const xs = [...new Set(rows.map((p) => p.x))].sort((a, b) => a - b)
  const ys = [...new Set(rows.map((p) => p.y))].sort((a, b) => a - b)
  const empty = <T,>(fill: T) => ys.map(() => xs.map(() => fill))
  const z = empty<number | null>(null)
  const refs = empty('')
  const hovers = empty('')
  for (const p of rows) {
    const [i, j] = [ys.indexOf(p.y), xs.indexOf(p.x)]
    z[i][j] = p.z
    refs[i][j] = encodePoint({ datasetId: dataset.id, rowId: p.row.id, columnId: spec.z })
    hovers[i][j] = cellHover(dataset, p.row.id, spec.z, [`${nameOf(dataset, spec.x)} ${p.x}`, `${nameOf(dataset, spec.y)} ${p.y}`])
  }
  const [xTitle, yTitle, zTitle] = [
    spec.axes?.x?.label || nameOf(dataset, spec.x),
    spec.axes?.y?.label || nameOf(dataset, spec.y),
    spec.axes?.z?.label || nameOf(dataset, spec.z),
  ]
  const trace: Data = {
    type: spec.type,
    x: xs,
    y: ys,
    z,
    customdata: refs,
    hovertext: hovers,
    hovertemplate: '%{hovertext}<extra></extra>',
    colorscale: sequentialScale(theme),
    colorbar: { title: title(zTitle), tickfont: { color: CHART_INK[theme].muted } },
  } as Data
  const layout: Partial<Layout> = { ...baseLayout(theme) }
  if (spec.type === 'surface') {
    layout.scene = {
      xaxis: { ...axisStyle(theme), title: title(xTitle) },
      yaxis: { ...axisStyle(theme), title: title(yTitle) },
      zaxis: { ...axisStyle(theme), title: title(zTitle) },
    }
  } else {
    layout.xaxis = { ...axisStyle(theme), title: title(xTitle) }
    layout.yaxis = { ...axisStyle(theme), title: title(yTitle) }
  }
  return { traces: [trace], layout, warnings: [], seriesCount: 1 }
}

function parcoords(spec: Extract<GridSpec, { type: 'parcoords' }>, dataset: ResolvedDataset, theme: ChartTheme): Compiled {
  const dimensions = spec.dimensions.flatMap((id) => dataset.columns.filter((c) => c.id === id))
  const colorBy = dataset.columns.find((c) => c.id === spec.color_by)
  const needed = colorBy ? [...dimensions, colorBy] : dimensions
  const complete = dataset.rows.filter((row) => needed.every((c) => row.cells[c.id]?.value != null))
  const warnings = [
    ...(spec.dimensions.length > dimensions.length ? [counted(spec.dimensions.length - dimensions.length, 'axis')] : []),
    ...(complete.length < dataset.rows.length ? [`${dataset.rows.length - complete.length} rows without a value on every axis are left out`] : []),
  ]
  const values = (id: string) => complete.map((row) => row.cells[id].value as number)
  const trace: Data = {
    type: 'parcoords',
    dimensions: dimensions.map((c) => ({ label: escapeText(c.name), values: values(c.id) })),
    line: colorBy
      ? { color: values(colorBy.id), colorscale: sequentialScale(theme), showscale: true, colorbar: { title: title(colorBy.name) } }
      : { color: seriesColor(theme, 0) },
    labelfont: { color: CHART_INK[theme].text },
    tickfont: { color: CHART_INK[theme].muted },
  } as Data
  return { traces: [trace], layout: baseLayout(theme), warnings, seriesCount: 1 }
}

export function compileGridChart(spec: GridSpec, data: ResolvedData, theme: ChartTheme): Compiled {
  const dataset = data.datasets.find((d) => d.id === spec.dataset_id)
  const required = spec.type === 'heatmap' ? [spec.row_labels] : spec.type === 'parcoords' ? [] : [spec.x, spec.y, spec.z]
  if (!dataset || !required.every((id) => dataset.columns.some((c) => c.id === id))) {
    return { traces: [], layout: baseLayout(theme), warnings: [GONE], seriesCount: 0 }
  }
  if (spec.type === 'heatmap') return heatmap(spec, dataset, theme)
  if (spec.type === 'parcoords') return parcoords(spec, dataset, theme)
  return surface(spec, dataset, theme)
}
