import { describe, expect, it } from 'vitest'
import type { ChartSpec } from '@/api/client'
import { compileChart } from './compile'
import { sequentialScale } from './palette'
import { BERT, BERT_B, bertTable, data, F1, GRID, GX, GY, GZ, longGrid, STD, SYSTEM } from './testData'

type Trace = Record<string, unknown>
const first = (spec: ChartSpec, ...datasets: Parameters<typeof data>) => compileChart(spec, data(...datasets), 'light').traces[0] as Trace

describe('compileChart: grid charts', () => {
  it('draws a heatmap of the chosen columns, one row per label, with gaps between cells', () => {
    const spec: ChartSpec = { version: 1, type: 'heatmap', dataset_id: BERT, row_labels: SYSTEM, columns: [F1, STD] }
    const compiled = compileChart(spec, data(bertTable), 'light')
    expect(compiled.traces[0]).toMatchObject({
      type: 'heatmap',
      x: ['F1', 'Std'],
      y: ['BERT-B', 'BERT-L'],
      z: [
        [88.5, 0.4],
        [90.9, 0.2],
      ],
      xgap: 2,
      ygap: 2,
      colorscale: sequentialScale('light'),
    })
    expect((compiled.traces[0] as Trace).customdata).toEqual([
      [`${BERT}|${BERT_B}|${F1}`, `${BERT}|${BERT_B}|${STD}`],
      [`${BERT}|${bertTable.rows[1].id}|${F1}`, `${BERT}|${bertTable.rows[1].id}|${STD}`],
    ])
    expect(compiled.layout.yaxis).toMatchObject({ autorange: 'reversed', title: { text: 'System' } })
  })

  it('pivots long-format rows into a surface grid, leaving missing points empty', () => {
    const spec: ChartSpec = { version: 1, type: 'surface', dataset_id: GRID, x: GX, y: GY, z: GZ }
    const compiled = compileChart(spec, data(longGrid), 'light')
    expect(compiled.traces[0]).toMatchObject({
      type: 'surface',
      x: [1, 2],
      y: [10, 20],
      z: [
        [0.9, 0.7],
        [0.5, null],
      ],
    })
    expect(compiled.layout.scene?.zaxis).toMatchObject({ title: { text: 'loss' } })
  })

  it('draws a contour on plain axes', () => {
    const compiled = compileChart({ version: 1, type: 'contour', dataset_id: GRID, x: GX, y: GY, z: GZ }, data(longGrid), 'light')
    expect(compiled.traces[0]).toMatchObject({ type: 'contour' })
    expect(compiled.layout.xaxis).toMatchObject({ title: { text: 'lr' } })
    expect(compiled.layout.scene).toBeUndefined()
  })

  it('draws parallel coordinates, coloured by a column, leaving out rows without every value', () => {
    const spec: ChartSpec = { version: 1, type: 'parcoords', dataset_id: BERT, dimensions: [F1, STD], color_by: STD }
    expect(first(spec, bertTable)).toMatchObject({
      type: 'parcoords',
      dimensions: [
        { label: 'F1', values: [88.5, 90.9] },
        { label: 'Std', values: [0.4, 0.2] },
      ],
      line: { color: [0.4, 0.2], showscale: true },
    })
    const withLabels: ChartSpec = { version: 1, type: 'parcoords', dataset_id: BERT, dimensions: [SYSTEM, F1] }
    const compiled = compileChart(withLabels, data(bertTable), 'light')
    expect(compiled.warnings).toEqual(['2 rows without a value on every axis are left out'])
  })

  it("says the chart's data is gone when its dataset or a required column is", () => {
    const spec: ChartSpec = { version: 1, type: 'heatmap', dataset_id: BERT, row_labels: SYSTEM, columns: [F1] }
    expect(compileChart(spec, data(), 'light')).toMatchObject({ traces: [], warnings: ["This chart's data is gone"], seriesCount: 0 })
    const lostColumn = compileChart({ ...spec, columns: [F1, GZ] }, data(bertTable), 'light')
    expect(lostColumn.warnings).toEqual(['1 column lost its data'])
  })

  it('runs the magnitude ramp the other way in the dark theme', () => {
    expect(sequentialScale('dark')[0]).toEqual([0, sequentialScale('light').at(-1)![1]])
  })
})
