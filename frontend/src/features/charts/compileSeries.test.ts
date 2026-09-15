import { describe, expect, it } from 'vitest'
import { symlog } from './chartMath'
import { compileChart } from './compile'
import { SERIES_COLORS } from './palette'
import { BERT, BERT_B, bertTable, cell, data, F1, MINE, ownData, RUN, SCORE, series, seriesChart, STD, SYSTEM } from './testData'

type Trace = Record<string, unknown> & { x?: unknown[]; y?: unknown[]; error_y?: Record<string, unknown> }
const traces = (compiled: { traces: unknown[] }) => compiled.traces as Trace[]

describe('compileChart: series charts', () => {
  it('draws one bar trace per series, labelled by the x column, with every point pointing at its cell', () => {
    const spec = seriesChart('bar', [series(), series({ id: 's2', dataset_id: MINE, x: RUN, y: SCORE })])
    const compiled = compileChart(spec, data(bertTable, ownData), 'light')

    const [bert, mine] = traces(compiled)
    expect(bert).toMatchObject({ type: 'bar', name: 'F1', x: ['BERT-B', 'BERT-L'], y: [88.5, 90.9] })
    expect(mine).toMatchObject({ name: 'Score (%)', x: ['mine'], y: [92] })
    expect(bert.customdata).toEqual([`${BERT}|${BERT_B}|${F1}`, `${BERT}|${bertTable.rows[1].id}|${F1}`])
    expect(compiled.seriesCount).toBe(2)
    expect(compiled.layout.showlegend).toBe(true)
    expect(compiled.layout.xaxis).toMatchObject({ type: 'category', title: { text: 'System' } })
    expect(compiled.layout.barmode).toBe('group')
  })

  it("hovers the raw text first, marks an edited cell, and names the point's source page", () => {
    const [bert] = traces(compileChart(seriesChart('bar', [series()]), data(bertTable), 'light'))
    expect(bert.hovertext).toEqual([
      '<b>88.5 ± 0.3</b><br>F1 · BERT-B<br>BERT · p. 6 · Table 2',
      '<b>90.9</b> · edited<br>F1 · BERT-L<br>BERT · p. 7 · Table 2',
    ])
    expect(bert.hovertemplate).toBe('%{hovertext}<extra></extra>')
  })

  it('hides the legend for a single series, whose title names it', () => {
    expect(compileChart(seriesChart('bar', [series()]), data(bertTable), 'light').layout.showlegend).toBe(false)
  })

  it('multiplies values and says so in the legend', () => {
    const [bert] = traces(compileChart(seriesChart('bar', [series({ multiply: 100, error: 'cells' })]), data(bertTable), 'light'))
    expect(bert.name).toBe('F1 ×100')
    expect(bert.y).toEqual([8850, 9090])
    expect(bert.error_y).toMatchObject({ array: [30, 0] })
  })

  it('draws error bars from the cells, from another column, or not at all', () => {
    const errors = (error: string) =>
      traces(compileChart(seriesChart('bar', [series({ error })]), data(bertTable), 'light'))[0].error_y
    expect(errors('cells')).toMatchObject({ type: 'data', array: [0.3, 0], visible: true })
    expect(errors(STD)).toMatchObject({ array: [0.4, 0.2] })
    expect(errors('none')).toBeUndefined()
  })

  it('sets a log axis, and transforms a symlog axis with ticks in real values', () => {
    const log = compileChart(seriesChart('bar', [series()], { axes: { y: { label: '', scale: 'log' } } }), data(bertTable), 'light')
    expect(log.layout.yaxis).toMatchObject({ type: 'log' })

    const spec = seriesChart('bar', [series({ error: 'cells' })], { axes: { y: { label: 'F1 score', scale: 'symlog' } } })
    const compiled = compileChart(spec, data(bertTable), 'light')
    const [bert] = traces(compiled)
    expect(bert.y).toEqual([symlog(88.5), symlog(90.9)])
    expect(compiled.layout.yaxis).toMatchObject({ type: 'linear', title: { text: 'F1 score' }, ticktext: ['0', '1', '10'] })
    expect(bert.error_y).toMatchObject({ symmetric: false })
    expect((bert.error_y!.array as number[])[0]).toBeCloseTo(symlog(88.8) - symlog(88.5))
  })

  it('adds a linear trend line with R² for a scatter, and none without two points', () => {
    const spec = seriesChart('scatter', [series({ x: STD, trend: 'linear' })])
    const [points, trend] = traces(compileChart(spec, data(bertTable), 'light'))
    expect(points).toMatchObject({ type: 'scatter', mode: 'markers', x: [0.4, 0.2] })
    expect(trend).toMatchObject({ mode: 'lines', name: 'F1 · linear trend (R² 1.00)', x: [0.2, 0.4], hoverinfo: 'skip' })
    expect((trend.y as number[])[0]).toBeCloseTo(90.9)

    const one = seriesChart('scatter', [series({ dataset_id: MINE, x: RUN, y: SCORE, trend: 'linear' })])
    expect(traces(compileChart(one, data(ownData), 'light'))).toHaveLength(1)
  })

  it('reads a text-only x column as categories on a line chart', () => {
    const compiled = compileChart(seriesChart('line', [series()]), data(bertTable), 'light')
    expect(traces(compiled)[0]).toMatchObject({ mode: 'lines+markers', x: ['BERT-B', 'BERT-L'] })
    expect(compiled.layout.xaxis).toMatchObject({ type: 'category' })
  })

  it('splits series into small multiples, one panel each, all in the first colour', () => {
    const spec = seriesChart('bar', [series(), series({ id: 's2', y: STD })], { layout: { barmode: 'group', facet: 'series', facet_columns: 2 } })
    const compiled = compileChart(spec, data(bertTable), 'light')
    const [first, second] = traces(compiled)
    expect(compiled.layout.grid).toEqual({ rows: 1, columns: 2, pattern: 'independent' })
    expect(second).toMatchObject({ xaxis: 'x2', yaxis: 'y2' })
    expect(first.marker).toMatchObject({ color: SERIES_COLORS.light[0] })
    expect(second.marker).toMatchObject({ color: SERIES_COLORS.light[0] })
    expect(compiled.layout.annotations?.map((a) => a.text)).toEqual(['F1', 'Std'])
    expect(compiled.layout.showlegend).toBe(false)
  })

  it('draws the series it still has data for and warns about the rest', () => {
    const spec = seriesChart('bar', [series(), series({ id: 's2', dataset_id: MINE, x: RUN, y: SCORE })])
    const compiled = compileChart(spec, data(bertTable), 'light')
    expect(compiled.warnings).toEqual(['1 series lost its data'])
    expect(compiled.seriesCount).toBe(1)

    const gone = compileChart(spec, data(), 'light')
    expect(gone.traces).toEqual([])
    expect(gone.warnings).toEqual(['2 series lost their data'])
  })

  it('uses the dark palette and dark ink in the dark theme', () => {
    const compiled = compileChart(seriesChart('bar', [series()]), data(bertTable), 'dark')
    expect(traces(compiled)[0].marker).toMatchObject({ color: SERIES_COLORS.dark[0] })
    expect(compiled.layout.font).toMatchObject({ color: '#f1f5f9' })
  })

  it('keeps a series colour the owner picked', () => {
    const [bert] = traces(compileChart(seriesChart('bar', [series({ color: '#123456' })]), data(bertTable), 'light'))
    expect(bert.marker).toMatchObject({ color: '#123456' })
  })

  it('draws a box per series and a 3D scatter in a scene', () => {
    expect(traces(compileChart(seriesChart('box', [series({ x: null })]), data(bertTable), 'light'))[0]).toMatchObject({
      type: 'box',
      x: undefined,
      y: [88.5, 90.9],
      boxpoints: 'all',
    })
    const spec = seriesChart('scatter3d', [series({ x: STD, y: F1, z: STD })])
    const compiled = compileChart(spec, data(bertTable), 'light')
    expect(traces(compiled)[0]).toMatchObject({ type: 'scatter3d', x: [0.4, 0.2], y: [88.5, 90.9], z: [0.4, 0.2] })
    expect(compiled.layout.scene?.zaxis).toMatchObject({ title: { text: 'Std' } })
  })

  it('escapes names so text from a PDF or CSV header is never markup', () => {
    const [bert] = traces(compileChart(seriesChart('bar', [series({ name: '<b>F1</b> & co' })]), data(bertTable), 'light'))
    expect(bert.name).toBe('&lt;b&gt;F1&lt;/b&gt; &amp; co')
  })

  it('escapes category labels on bars, boxes, categorical lines and their trend lines', () => {
    const label = '<a href="x">A</a> & <b>B</b>'
    const escaped = '&lt;a href="x"&gt;A&lt;/a&gt; &amp; &lt;b&gt;B&lt;/b&gt;'
    const marked: typeof bertTable = {
      ...bertTable,
      rows: bertTable.rows.map((row, i) => ({ ...row, cells: { ...row.cells, [SYSTEM]: cell(i === 0 ? label : 'plain', null) } })),
    }
    const xs = (type: 'bar' | 'box' | 'line') =>
      traces(compileChart(seriesChart(type, [series({ trend: 'linear' })]), data(marked), 'light')).map((t) => t.x)
    expect(xs('bar')[0]).toEqual([escaped, 'plain'])
    expect(xs('box')[0]).toEqual([escaped, 'plain'])
    const [line, trend] = xs('line')
    expect(line).toEqual([escaped, 'plain'])
    expect(trend).toEqual([escaped, 'plain'])
  })

  it('draws trend lines only when both axes are linear, and says why otherwise', () => {
    for (const axes of [{ y: { label: '', scale: 'log' as const } }, { x: { label: '', scale: 'symlog' as const } }]) {
      const compiled = compileChart(seriesChart('scatter', [series({ x: STD, trend: 'linear' })], { axes }), data(bertTable), 'light')
      expect(traces(compiled)).toHaveLength(1)
      expect(compiled.warnings).toEqual(['Trend lines are drawn on linear axes only'])
    }
    const plain = compileChart(seriesChart('scatter', [series({ x: STD })], { axes: { y: { label: '', scale: 'log' } } }), data(bertTable), 'light')
    expect(plain.warnings).toEqual([])
  })

  it('charts only the chosen rows, labelling rows without an x column by position', () => {
    const [bert] = traces(compileChart(seriesChart('bar', [series({ x: null, rows: [BERT_B] })]), data(bertTable), 'light'))
    expect(bert).toMatchObject({ x: ['Row 1'], y: [88.5] })
    expect(SYSTEM).toBeTruthy()
  })
})
