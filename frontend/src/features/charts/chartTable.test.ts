import { describe, expect, it } from 'vitest'
import { chartTable } from './chartTable'
import { BERT, bertTable, data, F1, MINE, ownData, SCORE, series, seriesChart, SYSTEM } from './testData'

describe('chartTable', () => {
  it("lists each series' points with the raw text, edits marked, and their sources", () => {
    const spec = seriesChart('bar', [series({ multiply: 100 }), series({ id: 's2', dataset_id: MINE, x: null, y: SCORE })])
    expect(chartTable(spec, data(bertTable, ownData))).toEqual({
      columns: ['Series', 'Label', 'Value', 'Source'],
      rows: [
        ['F1 ×100', 'BERT-B', '88.5 ± 0.3', 'BERT · p. 6 · Table 2'],
        ['F1 ×100', 'BERT-L', '90.9 (edited)', 'BERT · p. 7 · Table 2'],
        ['Score (%)', 'Row 1', '92', 'My data · runs.csv'],
      ],
    })
  })

  it("lists a grid chart's columns as they are in the dataset", () => {
    expect(chartTable({ version: 1, type: 'heatmap', dataset_id: BERT, row_labels: SYSTEM, columns: [F1] }, data(bertTable))).toEqual({
      columns: ['System', 'F1'],
      rows: [
        ['BERT-B', '88.5 ± 0.3'],
        ['BERT-L', '90.9 (edited)'],
      ],
    })
    expect(chartTable({ version: 1, type: 'heatmap', dataset_id: BERT, row_labels: SYSTEM, columns: [F1] }, data())).toEqual({ columns: [], rows: [] })
  })
})
