import { describe, expect, it } from 'vitest'
import type { DatasetSummary } from '@/api/client'
import { datasetMeta, datasetSource } from './datasetMeta'

const summary = (fields: Partial<DatasetSummary>): DatasetSummary => ({
  id: 'd',
  name: 'Table 2',
  kind: 'table',
  paper_id: 'p',
  paper_title: 'BERT',
  page: 7,
  region: [70, 60, 290, 240],
  row_count: 3,
  column_count: 1,
  created_at: '2026-09-14T10:00:00Z',
  updated_at: '2026-09-14T10:00:00Z',
  ...fields,
})

describe('datasetMeta', () => {
  it('gives a table its page and size, and a numbers dataset its count', () => {
    expect(datasetMeta(summary({}))).toBe('p. 7 · 3 rows × 1 column')
    expect(datasetMeta(summary({ kind: 'numbers', page: null, region: null, row_count: 1, column_count: 3 }))).toBe('1 number')
    expect(datasetMeta(summary({ kind: 'user', paper_id: null, page: null, region: null, row_count: 1, column_count: 2 }))).toBe(
      '1 row × 2 columns',
    )
  })
})

describe('datasetSource', () => {
  it("names the paper, the owner's own data, or a paper that has been deleted", () => {
    expect(datasetSource(summary({}))).toBe('BERT')
    expect(datasetSource(summary({ kind: 'user', paper_id: null, paper_title: null }))).toBe('My data')
    expect(datasetSource(summary({ paper_id: null, paper_title: null }))).toBe('Source paper deleted')
  })
})
