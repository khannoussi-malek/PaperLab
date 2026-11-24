import { useMemo } from 'react'
import { useDataset, usePaperDatasets } from '@/services/queries'
import { numberMarks, tableMarks } from '@/features/datasets/pageMarks'

/** The captured-table and number marks drawn on the pages, grouped by page. */
export function useReaderMarks(paperId: string) {
  const datasets = usePaperDatasets(paperId)
  const tableMarksByPage = useMemo(() => tableMarks(datasets.data ?? []), [datasets.data])
  const numbersDatasetId = datasets.data?.find((d) => d.kind === 'numbers')?.id ?? null
  const numbersDataset = useDataset(numbersDatasetId)
  const numberMarksByPage = useMemo(() => numberMarks(numbersDataset.data), [numbersDataset.data])
  return { tableMarksByPage, numberMarksByPage }
}
