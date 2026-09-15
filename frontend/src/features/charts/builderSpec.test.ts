import { describe, expect, it } from 'vitest'
import type { Dataset } from '@/api/client'
import { changeType, columnInfo, copyTitle, newSeries, nextSeriesId, panelProblem, quickChartSpec, specDatasetIds } from './builderSpec'
import { id } from './testData'

/** A saved dataset as the API returns it: `cells` is a list per row, each naming its column. */
function dataset(columns: string[], rows: (string | [string, number | null, number?])[][], datasetId = id(1)): Dataset {
  return {
    id: datasetId,
    name: 'Table 1',
    kind: 'table',
    paper_id: id(900),
    paper_title: 'BERT',
    page: 2,
    region: [0, 0, 1, 1],
    row_count: rows.length,
    column_count: columns.length,
    created_at: '2026-09-15T00:00:00Z',
    updated_at: '2026-09-15T00:00:00Z',
    charts: [],
    columns: columns.map((name, i) => ({ id: id(10 + i), position: i, name, unit: null })),
    rows: rows.map((cells, r) => ({
      id: id(100 + r),
      position: r,
      cells: cells.map((cell, c) => {
        const [raw, value, error] = typeof cell === 'string' ? [cell, null, null] : cell
        return { column_id: id(10 + c), raw, value, error: error ?? null, origin: 'extracted', original_raw: null, page: 2, bbox: null }
      }),
    })),
  }
}

const table = dataset(
  ['System', 'Dev F1', 'Test F1'],
  [
    ['BERT-B', ['88.5 ± 0.3', 88.5, 0.3], ['89.0', 89]],
    ['BERT-L', ['90.9', 90.9], ['91.2', 91.2]],
  ],
)

describe('builder specs', () => {
  it('describes columns: numbers or text, ± errors, and sample values', () => {
    expect(columnInfo(table)).toEqual([
      { id: id(10), name: 'System', numeric: false, hasErrors: false, samples: ['BERT-B', 'BERT-L'] },
      { id: id(11), name: 'Dev F1', numeric: true, hasErrors: true, samples: ['88.5 ± 0.3', '90.9'] },
      { id: id(12), name: 'Test F1', numeric: true, hasErrors: false, samples: ['89.0', '91.2'] },
    ])
  })

  it('describes a dataset object once: the builder asks on every render', () => {
    const first = columnInfo(table)
    expect(columnInfo(table)).toBe(first)
    expect(columnInfo({ ...table })).not.toBe(first)
    expect(columnInfo({ ...table })).toEqual(first)
  })

  it('names a copy within the 200-character title limit, like a duplicate made on the server', () => {
    expect(copyTitle('Results')).toBe('Results (copy)')
    const long = copyTitle('x'.repeat(200))
    expect(long).toHaveLength(200)
    expect(long).toBe(`${'x'.repeat(193)} (copy)`)
  })

  it('makes a quick bar chart of every number column against the first text column', () => {
    expect(quickChartSpec(table)).toEqual({
      version: 1,
      type: 'bar',
      layout: { barmode: 'group', facet: 'none', facet_columns: 2 },
      series: [
        { id: 's1', name: '', dataset_id: id(1), x: id(10), y: id(11), error: 'cells', trend: 'none', multiply: 1 },
        { id: 's2', name: '', dataset_id: id(1), x: id(10), y: id(12), error: 'none', trend: 'none', multiply: 1 },
      ],
    })
    expect(quickChartSpec(dataset(['Name'], [['a']]))).toBeNull()
  })

  it('splits a quick chart of more number columns than one panel holds into small multiples', () => {
    const wide = dataset(['Model', ...'abcdefg'.split('')], [['x', ...'1234567'.split('').map((n) => [n, Number(n)] as [string, number])]])
    expect(quickChartSpec(wide)?.layout).toMatchObject({ facet: 'series' })
  })

  it('adds a series on the next number column not yet charted, with a fresh id', () => {
    const [first] = quickChartSpec(table)!.series
    expect(newSeries(table, [first])).toMatchObject({ id: 's2', x: id(10), y: id(12), error: 'none' })
    expect(nextSeriesId([{ ...first, id: 's2' }])).toBe('s3')
    expect(newSeries(dataset(['Name'], [['a']]), [])).toBeNull()
  })

  it('switches between series types, dropping what the new type cannot draw', () => {
    const bar = quickChartSpec(table)!
    const scatter = changeType({ ...bar, series: [{ ...bar.series[0], trend: 'linear' }] }, 'scatter', table)
    expect(scatter).toMatchObject({ type: 'scatter', series: [{ trend: 'linear' }] })
    expect(changeType(scatter, 'bar', table)).toMatchObject({ type: 'bar', series: [{ trend: 'none', z: null }] })
    // 3D needs numbers on x and z: each series takes the other number column.
    expect(changeType(bar, 'scatter3d', table)).toMatchObject({
      type: 'scatter3d',
      series: [
        { x: id(12), y: id(11), z: id(12) },
        { x: id(11), y: id(12), z: id(11) },
      ],
    })
  })

  it("builds a grid chart from the first series' dataset", () => {
    const bar = quickChartSpec(table)!
    expect(changeType(bar, 'heatmap', table)).toMatchObject({ type: 'heatmap', dataset_id: id(1), row_labels: id(10), columns: [id(11), id(12)] })
    expect(changeType(bar, 'parcoords', table)).toMatchObject({ type: 'parcoords', dimensions: [id(11), id(12)], color_by: null })
    expect(changeType(bar, 'contour', table)).toBeNull()
    const long = dataset(['x', 'y', 'z'], [[['1', 1], ['2', 2], ['3', 3]]])
    expect(changeType(null, 'surface', long)).toMatchObject({ type: 'surface', x: id(10), y: id(11), z: id(12) })
    expect(changeType(null, 'bar', null)).toBeNull()
  })

  it('lists the datasets a spec reads', () => {
    const bar = quickChartSpec(table)!
    expect(specDatasetIds(bar)).toEqual([id(1)])
    expect(specDatasetIds(changeType(bar, 'heatmap', table))).toEqual([id(1)])
    expect(specDatasetIds(null)).toEqual([])
  })

  it('says why a spec cannot be saved yet: no series, or more series in one panel than can be told apart', () => {
    const bar = quickChartSpec(table)!
    expect(panelProblem(null)).toBe('Add a series to start the chart.')
    expect(panelProblem(bar)).toBeNull()
    const four = [0, 1, 2, 3].map((i) => ({ ...bar.series[0], id: `s${i + 1}` }))
    expect(panelProblem({ ...bar, type: 'scatter', series: four })).toBe(
      'Scatter charts show at most 3 series in one panel. Turn on small multiples, or remove a series.',
    )
    expect(panelProblem({ ...bar, type: 'scatter', series: four, layout: { barmode: 'group', facet: 'series', facet_columns: 2 } })).toBeNull()
    expect(panelProblem({ ...bar, type: 'scatter3d', series: four })).toBe('3D scatter charts show at most 3 series in one panel. Remove a series.')
    expect(panelProblem(changeType(bar, 'heatmap', table))).toBeNull()
  })
})
