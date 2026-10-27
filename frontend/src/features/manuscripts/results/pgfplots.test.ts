import { describe, expect, it } from 'vitest'
import type { ChartSpec } from '@/api/client'
import { F1, MINE, RUN, SCORE, STD, bertTable, cell, data, id, ownData, series, seriesChart } from '@/features/charts/testData'
import { pgfplotsSupport, toPgfplots } from './pgfplots'

const opts = { caption: 'F1 by system_', label: 'fig:f1' }
const render = (spec: ChartSpec, ...d: Parameters<typeof data>) => toPgfplots(spec, data(...d), opts)

describe('toPgfplots', () => {
  it('writes a grouped bar chart as a full figure', () => {
    const tex = render(seriesChart('bar', [series()]), bertTable)
    expect(tex.startsWith('\\begin{figure}[t]\n  \\centering\n  \\begin{tikzpicture}')).toBe(true)
    expect(tex).toContain('ybar,')
    expect(tex).not.toContain('stacked')
    expect(tex).toContain('width=\\linewidth')
    expect(tex).toContain('symbolic x coords={BERT-B,BERT-L}')
    expect(tex).toContain('xtick=data')
    expect(tex).toContain('xlabel={System}')
    expect(tex).toContain('ylabel={F1}')
    expect(tex).toContain('\\addplot table[col sep=comma, row sep=\\\\, x=x, y=y] {')
    expect(tex).toContain('BERT-B,88.5')
    expect(tex).not.toContain('\\addlegendentry')
    expect(tex).toContain('\\caption{F1 by system\\_}')
    expect(tex.endsWith('\\label{fig:f1}\n\\end{figure}')).toBe(true)
  })

  it('stacks bars when the layout says so and adds a legend for several series', () => {
    const spec = seriesChart('bar', [series({ name: 'F1' }), series({ id: 's2', y: STD, name: 'Std' })], { layout: { barmode: 'stack', facet: 'none', facet_columns: 2 } })
    const tex = render(spec, bertTable)
    expect(tex).toContain('ybar stacked,')
    expect(tex).toContain('\\addlegendentry{F1}')
    expect(tex).toContain('\\addlegendentry{Std}')
  })

  it('draws lines and scatter points from numbers', () => {
    expect(render(seriesChart('line', [series({ x: STD })]), bertTable)).not.toContain('only marks')
    const scatter = render(seriesChart('scatter', [series({ x: STD })]), bertTable)
    expect(scatter).toContain('only marks,')
    expect(scatter).not.toContain('symbolic')
    expect(scatter).toContain('0.4,88.5')
  })

  it('adds error bars for a series that has errors, zero where a row has none', () => {
    const tex = render(seriesChart('bar', [series({ error: 'cells' })]), bertTable)
    expect(tex).toContain('\\addplot[error bars/.cd, y dir=both, y explicit] table[col sep=comma, row sep=\\\\, x=x, y=y, y error=err]')
    expect(tex).toContain('BERT-B,88.5,0.3')
    expect(tex).toContain('BERT-L,90.9,0')
  })

  it('uses log axes when the spec says so', () => {
    const tex = render(seriesChart('scatter', [series({ x: STD })], { axes: { x: { label: '', scale: 'log' }, y: { label: 'F1 score', scale: 'log' } } }), bertTable)
    expect(tex).toContain('ymode=log')
    expect(tex).toContain('xmode=log')
    expect(tex).toContain('ylabel={F1 score}')
  })

  it('writes one addplot per series, each with its own table, when series use different datasets or rows', () => {
    const spec = seriesChart('bar', [series({ rows: [id(101)] }), series({ id: 's2', dataset_id: MINE, x: RUN, y: SCORE })])
    const tex = render(spec, bertTable, ownData)
    expect(tex.match(/\\addplot/g)).toHaveLength(2)
    expect(tex).toContain('symbolic x coords={BERT-B,mine}')
    expect(tex).toContain('BERT-B,88.5')
    expect(tex).not.toContain('BERT-L,')
    expect(tex).toContain('mine,92')
    expect(tex).toContain('\\addlegendentry{Score (\\%)}')
  })

  it('multiplies values as the chart shows them and drops trend lines', () => {
    const spec = seriesChart('scatter', [series({ x: STD, multiply: 100, trend: 'linear' })])
    const tex = render(spec, bertTable)
    expect(tex).toContain('0.4,8850')
    expect(tex).not.toContain('trend')
    expect(pgfplotsSupport(spec)).toEqual({ ok: true, notes: ["Trend lines aren't drawn in LaTeX."] })
  })

  it('strips commas and braces from category names and escapes the rest', () => {
    const odd = { ...bertTable, rows: [{ ...bertTable.rows[0], cells: { ...bertTable.rows[0].cells, [bertTable.columns[0].id]: cell('A, {b} c_d', null) } }] }
    const tex = render(seriesChart('bar', [series()]), odd)
    expect(tex).toContain('symbolic x coords={A b c\\_d}')
    expect(tex).toContain('A b c\\_d,88.5')
    expect(tex).not.toMatch(/coords=\{[^}]*,/)
  })

  it('escapes the series name, axis labels and keeps the multiplier visible', () => {
    const spec = seriesChart('bar', [series({ name: 'F1 & co', multiply: 2 }), series({ id: 's2', y: STD })], { axes: { y: { label: '100% sure', scale: 'linear' } } })
    const tex = render(spec, bertTable)
    expect(tex).toContain('\\addlegendentry{F1 \\& co $\\times$2}')
    expect(tex).toContain('ylabel={100\\% sure}')
  })
})

describe('log axes', () => {
  const log = { y: { label: '', scale: 'log' as const } }

  it('pads a narrow range out to the surrounding powers of ten, which is what keeps TeX from overflowing', () => {
    const tex = render(seriesChart('bar', [series()], { axes: log }), bertTable)
    expect(tex).toContain('ymode=log,\n    ymin=1e1,\n    ymax=1e2,')
  })

  it('pads x too, and keeps a single power of ten from collapsing to an empty range', () => {
    const spec = seriesChart('scatter', [series({ x: STD, multiply: 1 })], { axes: { x: { label: '', scale: 'log' }, y: { label: '', scale: 'log' } } })
    const tex = render(spec, bertTable)
    expect(tex).toContain('xmin=1e-1,\n    xmax=1e0')
    expect(tex).toContain('ymin=1e1,\n    ymax=1e2')
    const exact = seriesChart('scatter', [series({ x: STD, multiply: 10 })], { axes: log })
    expect(render(exact, bertTable)).toContain('ymin=1e2,\n    ymax=1e3')
  })

  it('sends zero, negative and error-bar-reaching-zero values to a picture', () => {
    const reason = "A log axis can't show zero or negative values, so it goes in as a picture."
    const zero = seriesChart('bar', [series({ multiply: 0 })], { axes: log })
    expect(pgfplotsSupport(zero, data(bertTable))).toEqual({ ok: false, reason })
    const negative = seriesChart('bar', [series({ multiply: -1 })], { axes: log })
    expect(pgfplotsSupport(negative, data(bertTable))).toEqual({ ok: false, reason })
    const xLog = seriesChart('scatter', [series({ x: STD, y: STD })], { axes: { x: { label: '', scale: 'log' }, y: { label: '', scale: 'linear' } } })
    expect(pgfplotsSupport(xLog, data(bertTable))).toEqual({ ok: true, notes: [] })
    const xNeg = { ...bertTable, rows: bertTable.rows.map((r) => ({ ...r, cells: { ...r.cells, [STD]: cell('0', 0) } })) }
    expect(pgfplotsSupport(xLog, data(xNeg))).toEqual({ ok: false, reason })
  })
})

describe('empty and partial data', () => {
  it('is not ok when no series can be drawn', () => {
    const lost = seriesChart('bar', [series({ dataset_id: MINE })])
    const support = pgfplotsSupport(lost, data(bertTable))
    expect(support.ok).toBe(false)
    expect(() => render(lost, bertTable)).toThrow()
  })

  it('leaves out categories that no series has a value for', () => {
    const blank = { ...bertTable, rows: [bertTable.rows[0], { ...bertTable.rows[1], cells: { ...bertTable.rows[1].cells, [F1]: cell('', null) } }] }
    const tex = render(seriesChart('bar', [series()]), blank)
    expect(tex).toContain('symbolic x coords={BERT-B}')
  })
})

describe('pgfplotsSupport', () => {
  it('supports bar, line and scatter', () => {
    for (const t of ['bar', 'line', 'scatter'] as const) expect(pgfplotsSupport(seriesChart(t, [series()]))).toEqual({ ok: true, notes: [] })
  })

  it('sends every other type, small multiples and symlog to a picture with the reason', () => {
    const reason = "pgfplots can't draw this chart type, so it goes in as a picture."
    const bad: ChartSpec[] = [
      seriesChart('box', [series()]),
      seriesChart('scatter3d', [series()]),
      seriesChart('bar', [series()], { layout: { barmode: 'group', facet: 'series', facet_columns: 2 } }),
      seriesChart('bar', [series()], { axes: { y: { label: '', scale: 'symlog' } } }),
      { version: 1, type: 'heatmap' } as unknown as ChartSpec,
      { version: 1, type: 'surface' } as unknown as ChartSpec,
      { version: 1, type: 'contour' } as unknown as ChartSpec,
      { version: 1, type: 'parcoords' } as unknown as ChartSpec,
    ]
    for (const spec of bad) expect(pgfplotsSupport(spec)).toEqual({ ok: false, reason })
  })
})
