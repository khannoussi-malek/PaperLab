import { describe, expect, it } from 'vitest'
import type { Dataset, DatasetSummary } from '@/api/client'
import { dragRegion, MARKER_PT, numberMarks, tableMarkerAt, tableMarks } from './pageMarks'

const summary = (overrides: Partial<DatasetSummary>): DatasetSummary => ({
  id: 'd1',
  name: 'Table 1: Results.',
  kind: 'table',
  paper_id: 'p1',
  paper_title: 'Paper',
  page: 2,
  region: [72, 300, 400, 380],
  row_count: 2,
  column_count: 2,
  created_at: '',
  updated_at: '',
  ...overrides,
})

describe('page marks', () => {
  it("puts each captured table's outline and marker on its page, skipping numbers and own data", () => {
    const marks = tableMarks([summary({}), summary({ id: 'n', kind: 'numbers', page: null, region: null }), summary({ id: 'u', kind: 'user', page: null, region: null })])
    expect([...marks.keys()]).toEqual([2])
    expect(marks.get(2)).toEqual([{ datasetId: 'd1', name: 'Table 1: Results.', region: [72, 300, 400, 380], marker: [400 - MARKER_PT, 300, 400, 300 + MARKER_PT] }])
  })

  it("finds the table whose marker is under the pointer, not one whose body is", () => {
    const marks = tableMarks([summary({})]).get(2)!
    expect(tableMarkerAt(marks, [395, 305])?.datasetId).toBe('d1')
    expect(tableMarkerAt(marks, [100, 350])).toBeNull()
  })

  it("underlines each captured number on its own page", () => {
    const numbers = {
      rows: [
        { id: 'r1', position: 0, cells: [{ column_id: 'label', raw: 'F1', value: null, error: null, origin: 'human', original_raw: null, page: null, bbox: null }, { column_id: 'value', raw: '88.5', value: 88.5, error: 0.3, origin: 'extracted', original_raw: null, page: 3, bbox: [[100, 200, 140, 212]] }] },
        { id: 'r2', position: 1, cells: [{ column_id: 'value', raw: '7', value: 7, error: null, origin: 'human', original_raw: null, page: null, bbox: null }] },
      ],
    } as unknown as Dataset
    expect(numberMarks(numbers)).toEqual(new Map([[3, [{ rowId: 'r1', rects: [[100, 200, 140, 212]] }]]]))
    expect(numberMarks(undefined).size).toBe(0)
  })

  it('turns a drag in any direction into a box on the page, and a click into nothing', () => {
    expect(dragRegion([400, 380], [72, 300], { width: 612, height: 792 })).toEqual([72, 300, 400, 380])
    expect(dragRegion([500, 700], [700, 900], { width: 612, height: 792 })).toEqual([500, 700, 612, 792])
    expect(dragRegion([100, 100], [105, 300], { width: 612, height: 792 })).toBeNull()
  })
})
