import type { ChartSpec, ResolvedData, SeriesChartSpec, SeriesSpec } from '@/api/client'
import { columnName, isDrawable, seriesName, seriesPoints, type SeriesPoint } from '@/features/charts/seriesPoints'
import { latexEscape } from '../deck/latex'

export type PgfplotsSupport = { ok: true; notes: string[] } | { ok: false; reason: string }

const PICTURE_REASON = "pgfplots can't draw this chart type, so it goes in as a picture."
const TREND_NOTE = "Trend lines aren't drawn in LaTeX."
const SERIES_TYPES = new Set(['bar', 'line', 'scatter'])

const hasTrend = (spec: SeriesChartSpec) => spec.series.some((s) => s.trend === 'linear')
const isSeries = (spec: ChartSpec): spec is SeriesChartSpec => SERIES_TYPES.has(spec.type) && 'series' in spec

/** Whether a chart can be written as a pgfplots figure; if not, why it goes in as a picture instead. */
export function pgfplotsSupport(spec: ChartSpec): PgfplotsSupport {
  if (!isSeries(spec)) return { ok: false, reason: PICTURE_REASON }
  if (spec.layout?.facet === 'series') return { ok: false, reason: PICTURE_REASON }
  if ([spec.axes?.x?.scale, spec.axes?.y?.scale].includes('symlog')) return { ok: false, reason: PICTURE_REASON }
  return { ok: true, notes: hasTrend(spec) ? [TREND_NOTE] : [] }
}

/** A category name as it sits in a pgfplots coordinate list and a comma-separated table: no commas, braces or line breaks. */
const coord = (label: string) => latexEscape(label.replace(/[,{}\s]+/g, ' ').trim())

const text = (value: string) => latexEscape(value).replaceAll('×', '$\\times$')

type Live = { series: SeriesSpec; name: string; points: SeriesPoint[] }

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
  if (!isSeries(spec)) throw new Error(PICTURE_REASON)
  const byId = new Map(data.datasets.map((d) => [d.id, d]))
  const live: Live[] = spec.series.flatMap((series) => {
    const dataset = byId.get(series.dataset_id)
    if (!isDrawable(series, dataset)) return []
    return [{ series, name: seriesName(series, dataset), points: seriesPoints(series, dataset) }]
  })
  const first = live[0]
  const firstData = first ? byId.get(first.series.dataset_id) : undefined
  const categorical =
    spec.type === 'bar' ||
    spec.axes?.x?.scale === 'category' ||
    live.every((s) => s.series.x && s.points.every((p) => p.x === null))
  const labels = [...new Set(live.flatMap((s) => s.points.map((p) => coord(p.xLabel))))]
  const xTitle = spec.axes?.x?.label || (first?.series.x && firstData ? columnName(firstData, first.series.x) : '')
  const yTitle = spec.axes?.y?.label || (first && firstData ? columnName(firstData, first.series.y) : '')
  const kind = spec.type === 'bar' ? (spec.layout?.barmode === 'stack' ? 'ybar stacked' : 'ybar') : spec.type === 'scatter' ? 'only marks' : null
  const options = [
    kind,
    'width=\\linewidth',
    xTitle && `xlabel={${text(xTitle)}}`,
    yTitle && `ylabel={${text(yTitle)}}`,
    categorical && `symbolic x coords={${labels.join(',')}}`,
    categorical && 'xtick=data',
    !categorical && spec.axes?.x?.scale === 'log' && 'xmode=log',
    spec.axes?.y?.scale === 'log' && 'ymode=log',
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
