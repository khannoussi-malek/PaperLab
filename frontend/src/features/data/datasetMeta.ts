import type { DatasetSummary } from '@/api/client'

const counted = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

/** "p. 7 · 3 rows × 4 columns" for a captured table, "5 numbers" for the numbers picked from a paper's text. */
export function datasetMeta(dataset: Pick<DatasetSummary, 'kind' | 'page' | 'row_count' | 'column_count'>): string {
  if (dataset.kind === 'numbers') return counted(dataset.row_count, 'number')
  const size = `${counted(dataset.row_count, 'row')} × ${counted(dataset.column_count, 'column')}`
  return dataset.page ? `p. ${dataset.page} · ${size}` : size
}

/** Where a dataset's numbers come from, in words. */
export function datasetSource(dataset: Pick<DatasetSummary, 'kind' | 'paper_title'>): string {
  if (dataset.kind === 'user') return 'My data'
  return dataset.paper_title ?? 'Source paper deleted'
}
