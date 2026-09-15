import { describe, expect, it } from 'vitest'
import { decodePoint, encodePoint, pointSource, sourceHref, sourceLabel } from './points'
import { BERT, BERT_B, BERT_L, bertTable, data, F1, id, MINE, ownData, RUN_1, SCORE } from './testData'

describe('chart points', () => {
  it('round-trips a point reference and ignores anything else', () => {
    const ref = { datasetId: BERT, rowId: BERT_B, columnId: F1 }
    expect(decodePoint(encodePoint(ref))).toEqual(ref)
    expect(decodePoint('a|b')).toBeNull()
    expect(decodePoint(42)).toBeNull()
  })

  it("opens a paper cell on the cell's own page, not the table's first page or the row's position", () => {
    const source = pointSource(data(bertTable), { datasetId: BERT, rowId: BERT_L, columnId: F1 })
    expect(source).toEqual({ kind: 'paper', paperId: id(900), page: 7, rects: [[220, 20, 280, 30]] })
    expect(sourceHref(source!)).toBe(`#/papers/${id(900)}?tab=data&page=7&rects=220,20,280,30`)
  })

  it('opens own data, or a table whose paper was deleted, at the grid cell', () => {
    const own = pointSource(data(ownData), { datasetId: MINE, rowId: RUN_1, columnId: SCORE })
    expect(own).toEqual({ kind: 'dataset', datasetId: MINE, rowId: RUN_1, columnId: SCORE })
    expect(sourceHref(own!)).toBe(`#/datasets/${MINE}?row=${RUN_1}&column=${SCORE}`)

    const orphan = { ...bertTable, paper_id: null, paper_title: null }
    expect(pointSource(data(orphan), { datasetId: BERT, rowId: BERT_B, columnId: F1 })).toMatchObject({ kind: 'dataset' })
    expect(pointSource(data(bertTable), { datasetId: BERT, rowId: id(999), columnId: F1 })).toBeNull()
  })

  it('names a source in words', () => {
    expect(sourceLabel(bertTable, bertTable.rows[1].cells[F1])).toBe('BERT · p. 7 · Table 2')
    expect(sourceLabel(ownData)).toBe('My data · runs.csv')
    expect(sourceLabel({ ...bertTable, paper_title: null })).toBe('Source paper deleted · p. 6 · Table 2')
  })
})
