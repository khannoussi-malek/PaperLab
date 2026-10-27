import type { ChartSpec, ResolvedData, SeriesChartSpec, SeriesSpec } from '@/api/client'
import { columnName, isDrawable, seriesName, seriesPoints, type SeriesPoint } from '@/features/charts/seriesPoints'
import { latexEscape } from '../deck/latex'

export type PgfplotsSupport = { ok: true; notes: string[] } | { ok: false; reason: string }

const PICTURE_REASON = "pgfplots can't draw this chart type, so it goes in as a picture."
const TREND_NOTE = "Trend lines aren't drawn in LaTeX."
const SERIES_TYPES = new Set(['bar', 'line', 'scatter'])

const hasTrend = (spec: SeriesChartSpec) => spec.series.some((s) => s.trend === 'linear')
const isSeries = (spec: ChartSpec): spec is SeriesChartSpec => SERIES_TYPES.has(spec.type) && 'series' in spec

const LOG_REASON = "A log axis can't show zero or negative values, so it goes in as a picture."
const NO_DATA_REASON = 'No series in this chart has data to draw.'

type Live = { series: SeriesSpec; name: string; points: SeriesPoint[] }

function liveSeries(spec: SeriesChartSpec, data: ResolvedData): Live[] {
  const byId = new Map(data.datasets.map((d) => [d.id, d]))
  return spec.series.flatMap((series) => {
    const dataset = byId.get(series.dataset_id)
    if (!isDrawable(series, dataset)) return []
    return [{ series, name: seriesName(series, dataset), points: seriesPoints(series, dataset) }]
  })
}

const isCategorical = (spec: SeriesChartSpec, live: Live[]) =>
  spec.type === 'bar' || spec.axes?.x?.scale === 'category' || live.every((s) => s.series.x && s.points.every((p) => p.x === null))

/** The numbers a log axis has to show, error bar ends included. */
function axisValues(live: Live[], axis: 'x' | 'y'): number[] {
  return live.flatMap((s) =>
    s.points.flatMap((p) => {
      const v = axis === 'x' ? p.x : p.y
      if (v === null) return []
      return axis === 'y' && p.error !== null ? [v - p.error, v, v + p.error] : [v]
    }),
  )
}

/** Whether a chart can be written as a pgfplots figure; if not, why it goes in as a picture. With data, also checks the values. */
export function pgfplotsSupport(spec: ChartSpec, data?: ResolvedData): PgfplotsSupport {
  if (!isSeries(spec)) return { ok: false, reason: PICTURE_REASON }
  if (spec.layout?.facet === 'series') return { ok: false, reason: PICTURE_REASON }
  if ([spec.axes?.x?.scale, spec.axes?.y?.scale].includes('symlog')) return { ok: false, reason: PICTURE_REASON }
  if (data) {
    const live = liveSeries(spec, data)
    if (live.length === 0) return { ok: false, reason: NO_DATA_REASON }
    const logs = [
      spec.axes?.y?.scale === 'log' ? axisValues(live, 'y') : [],
      spec.axes?.x?.scale === 'log' && !isCategorical(spec, live) ? axisValues(live, 'x') : [],
    ]
    if (logs.some((values) => values.some((v) => v <= 0))) return { ok: false, reason: LOG_REASON }
  }
  return { ok: true, notes: hasTrend(spec) ? [TREND_NOTE] : [] }
}

/**
 * A log axis over a narrow range ("88.5 to 90.9") overflows TeX's dimensions, so the limits are padded out to the
 * surrounding powers of ten: tectonic compiles that, and the range then reads like any log plot.
 */
function logLimits(name: 'xmin' | 'ymin', values: number[]): string[] {
  if (values.length === 0) return []
  const low = Math.floor(Math.log10(Math.min(...values)) + 1e-9)
  const high = Math.max(Math.ceil(Math.log10(Math.max(...values)) - 1e-9), low + 1)
  const prefix = name[0]
  return [`${prefix}min=1e${low}`, `${prefix}max=1e${high}`]
}

/** A category name as it sits in a pgfplots coordinate list and a comma-separated table: no commas, braces or line breaks. */
const coord = (label: string) => latexEscape(label.replace(/[,{}\s]+/g, ' ').trim())

const text = (value: string) => latexEscape(value).replaceAll('×', '$\\times$')

function addPlot(s: Live, categorical: boolean, legend: boolean): string {
  const hasError = s.points.some((p) => p.error !== null)
  const rows = s.points.flatMap((p) => {
    const x = categorical ? coord(p.xLabel) : p.x
    if (p.y === null || x === null) return []
    return [[x, p.y, ...(hasError ? [p.error ?? 0] : [])].join(',')]
  })
  const options = hasError ? '[error bars/.cd, y dir=both, y explicit]' : ''
  const columns = `x=x, y=y${hasError ? ', y error=err' : ''}`
  const header = hasError ? 'x,y,err' : 'x,y'
  const body = [header, ...rows].map((r) => `${r}\\\\`).join('\n    ')
  return [
    `    \\addplot${options} table[col sep=comma, row sep=\\\\, ${columns}] {`,
    `    ${body}`,
    '    };',
    ...(legend ? [`    \\addlegendentry{${text(s.name)}}`] : []),
  ].join('\n')
}

/** The chart as a full `figure`: data embedded inline, one \addplot per series. Call only when pgfplotsSupport is ok. */
export function toPgfplots(spec: ChartSpec, data: ResolvedData, opts: { caption: string; label: string }): string {
  const support = pgfplotsSupport(spec, data)
  if (!support.ok) throw new Error(support.reason)
  if (!isSeries(spec)) throw new Error(PICTURE_REASON) // narrows the type; unreachable after the check
  const live = liveSeries(spec, data)
  const byId = new Map(data.datasets.map((d) => [d.id, d]))
  const first = live[0]
  const firstData = byId.get(first.series.dataset_id)
  const categorical = isCategorical(spec, live)
  // A category with no value in any series would be an empty slot on the axis.
  const labels = [...new Set(live.flatMap((s) => s.points.filter((p) => p.y !== null).map((p) => coord(p.xLabel))))]
  const xTitle = spec.axes?.x?.label || (first.series.x && firstData ? columnName(firstData, first.series.x) : '')
  const yTitle = spec.axes?.y?.label || (firstData ? columnName(firstData, first.series.y) : '')
  const kind = spec.type === 'bar' ? (spec.layout?.barmode === 'stack' ? 'ybar stacked' : 'ybar') : spec.type === 'scatter' ? 'only marks' : null
  const options = [
    kind,
    'width=\\linewidth',
    xTitle && `xlabel={${text(xTitle)}}`,
    yTitle && `ylabel={${text(yTitle)}}`,
    categorical && `symbolic x coords={${labels.join(',')}}`,
    categorical && 'xtick=data',
    ...(!categorical && spec.axes?.x?.scale === 'log' ? ['xmode=log', ...logLimits('xmin', axisValues(live, 'x'))] : []),
    ...(spec.axes?.y?.scale === 'log' ? ['ymode=log', ...logLimits('ymin', axisValues(live, 'y'))] : []),
    live.length > 1 && 'legend pos=outer north east',
  ].filter((o): o is string => typeof o === 'string' && o !== '')
  return [
    '\\begin{figure}[t]',
    '  \\centering',
    '  \\begin{tikzpicture}',
    '  \\begin{axis}[',
    options.map((o) => `    ${o},`).join('\n'),
    '  ]',
    live.map((s) => addPlot(s, categorical, live.length > 1)).join('\n'),
    '  \\end{axis}',
    '  \\end{tikzpicture}',
    `  \\caption{${latexEscape(opts.caption)}}`,
    `  \\label{${opts.label}}`,
    '\\end{figure}',
  ].join('\n')
}
