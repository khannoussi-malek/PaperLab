import { describe, expect, it } from 'vitest'
import type { Dataset, TablePreview } from '@/api/client'
import {
  chartsLosingColumns,
  deleteColumn,
  deleteRow,
  editCell,
  emptyGrid,
  fillDown,
  fromDataset,
  fromPreview,
  insertColumn,
  insertRow,
  isEdited,
  mergeColumns,
  renameColumn,
  splitColumn,
  toGridIn,
  useRowAsHeader,
  type Grid,
} from './gridModel'

type Rect = [number, number, number, number]
const rect = (x: number): Rect => [x, 100, x + 20, 110]
const read = (raw: string, x: number) => ({ raw, extracted: raw, page: 1, bbox: [rect(x)] })
const typed = (raw: string) => ({ raw, extracted: null, page: null, bbox: null })
const column = { id: null, name: '', unit: null }

/** A captured table: a header row, then two rows; every cell with text read from page 1. */
const preview: TablePreview = {
  name: 'Table 2: SQuAD 1.1 results.',
  grid: {
    columns: [column, column, column],
    rows: [
      { id: null, cells: [read('System', 72), read('Dev', 200), read('Test', 300)] },
      { id: null, cells: [read('BERT-B', 72), read('88.5', 200), read('87.0', 300)] },
      { id: null, cells: [read('BERT-L', 72), read('90.9', 200), typed('')] },
    ],
  },
}

const texts = (grid: Grid) => grid.rows.map((row) => row.cells.map((cell) => cell.raw))

describe('fromPreview and toGridIn', () => {
  it('gives every row and column a key, and sends the grid back without the keys', () => {
    const grid = fromPreview(preview)
    expect(grid.columns.map((c) => c.key)).toEqual(['c0', 'c1', 'c2'])
    expect(grid.rows.map((r) => r.key)).toEqual(['r0', 'r1', 'r2'])
    expect(toGridIn(grid)).toEqual(preview.grid)
  })
})

describe('fromDataset', () => {
  it('keeps the ids, and gives an edited extracted cell back the text extraction read', () => {
    const cell = (raw: string, origin: string, original_raw: string | null, page: number | null) => ({
      column_id: 'col-f1', raw, value: Number(raw), error: null, origin, original_raw, page, bbox: page ? [rect(1)] : null,
    })
    const dataset = {
      columns: [{ id: 'col-f1', position: 0, name: 'F1', unit: '%' }],
      rows: [
        { id: 'row-1', position: 0, cells: [cell('88.6', 'extracted', '88.5', 7)] },
        { id: 'row-2', position: 1, cells: [cell('92', 'human', null, null)] },
      ],
    } as unknown as Dataset

    const grid = fromDataset(dataset)

    expect(grid.columns).toEqual([{ key: 'col-f1', id: 'col-f1', name: 'F1', unit: '%' }])
    expect(grid.rows[0]).toEqual({ key: 'row-1', id: 'row-1', cells: [{ raw: '88.6', extracted: '88.5', page: 7, bbox: [rect(1)] }] })
    expect(grid.rows[1].cells[0]).toEqual(typed('92'))
    expect([isEdited(grid.rows[0].cells[0]), isEdited(grid.rows[1].cells[0])]).toEqual([true, false])
  })
})

describe('editing', () => {
  it('changes one cell without touching the grid it came from, and marks an extracted cell edited', () => {
    const grid = fromPreview(preview)
    const edited = editCell(grid, 1, 1, '88.6')
    expect(texts(edited)[1]).toEqual(['BERT-B', '88.6', '87.0'])
    expect(texts(grid)[1]).toEqual(['BERT-B', '88.5', '87.0'])
    expect(isEdited(edited.rows[1].cells[1])).toBe(true)
    expect(isEdited(editCell(edited, 1, 1, '88.5').rows[1].cells[1])).toBe(false)
  })

  it('uses a row as the header, joining it onto names already there', () => {
    const once = useRowAsHeader(fromPreview(preview), 0)
    expect(once.columns.map((c) => c.name)).toEqual(['System', 'Dev', 'Test'])
    expect(texts(once)).toEqual([['BERT-B', '88.5', '87.0'], ['BERT-L', '90.9', '']])
    expect(useRowAsHeader(once, 1).columns.map((c) => c.name)).toEqual(['System / BERT-L', 'Dev / 90.9', 'Test'])
  })

  it('merges a column into the one on its left: text and rects joined, the left id kept', () => {
    const base = fromPreview(preview)
    const saved: Grid = { ...base, columns: base.columns.map((c, i) => ({ ...c, id: `id-${i}` })) }
    const merged = mergeColumns(renameColumn(saved, 1, 'Dev'), 0)
    expect(merged.columns.map((c) => [c.id, c.name])).toEqual([['id-0', 'Dev'], ['id-2', '']])
    expect(merged.rows[1].cells[0]).toEqual({ raw: 'BERT-B 88.5', extracted: 'BERT-B 88.5', page: 1, bbox: [rect(72), rect(200)] })
    // An empty typed cell on the right adds nothing: the left cell stays exactly as it was.
    expect(mergeColumns(merged, 0).rows[2].cells[0]).toEqual(merged.rows[2].cells[0])
    expect(mergeColumns(merged, 1)).toBe(merged) // the last column has nothing to its right
  })

  it('splits a column after N words into a new column on its right', () => {
    const one = fromPreview({ name: null, grid: { columns: [column, column], rows: [{ id: null, cells: [read('Training WSJ 23 F1', 72), read('88.3', 300)] }] } })
    const split = splitColumn(one, 0, 1)
    expect(texts(split)).toEqual([['Training', 'WSJ 23 F1', '88.3']])
    expect(split.rows[0].cells[1]).toEqual({ raw: 'WSJ 23 F1', extracted: 'WSJ 23 F1', page: 1, bbox: [rect(72)] })
    expect(split.columns.map((c) => c.id)).toEqual([null, null, null])
    expect(new Set(split.columns.map((c) => c.key)).size).toBe(3)
    expect(splitColumn(one, 0, 9)).toBe(one) // no cell has more than 9 words: nothing to split off
  })

  it('fills empty cells from the one above, as typed values', () => {
    const labels = fromPreview({
      name: null,
      grid: { columns: [column], rows: [read('(A)', 72), typed(''), read('(B)', 72), typed(' ')].map((cell) => ({ id: null, cells: [cell] })) },
    })
    const filled = fillDown(labels, 0)
    expect(texts(filled)).toEqual([['(A)'], ['(A)'], ['(B)'], ['(B)']])
    expect([filled.rows[0].cells[0], filled.rows[1].cells[0]]).toEqual([read('(A)', 72), typed('(A)')])
  })

  it('inserts and deletes rows and columns, giving new ones fresh keys and no ids', () => {
    const grid = fromPreview(preview)
    const withRow = insertRow(grid, 1)
    expect(texts(withRow)[1]).toEqual(['', '', ''])
    expect(withRow.rows[1].id).toBeNull()
    expect(new Set(withRow.rows.map((r) => r.key)).size).toBe(4)
    expect(texts(deleteRow(withRow, 1))).toEqual(texts(grid))

    const withColumn = insertColumn(grid, 3)
    expect(texts(withColumn)[0]).toEqual(['System', 'Dev', 'Test', ''])
    expect(new Set(withColumn.columns.map((c) => c.key)).size).toBe(4)
    expect(texts(deleteColumn(withColumn, 0))[0]).toEqual(['Dev', 'Test', ''])
  })
})

describe('emptyGrid', () => {
  it('has typed cells only, under the column names given', () => {
    expect(toGridIn(emptyGrid(['Run', 'F1'], 2))).toEqual({
      columns: [{ id: null, name: 'Run', unit: null }, { id: null, name: 'F1', unit: null }],
      rows: [
        { id: null, cells: [typed(''), typed('')] },
        { id: null, cells: [typed(''), typed('')] },
      ],
    })
  })
})

describe('chartsLosingColumns', () => {
  it('names the charts that use a column the grid no longer has', () => {
    const grid: Grid = { columns: [{ key: 'a', id: 'col-a', name: 'A', unit: null }], rows: [] }
    const charts = [
      { id: 'kept', title: 'Kept', column_ids: ['col-a'] },
      { id: 'hit', title: 'Hit', column_ids: ['col-a', 'col-b'] },
    ]
    expect(chartsLosingColumns(charts, grid).map((c) => c.title)).toEqual(['Hit'])
  })
})
