import { useEffect, useMemo } from 'react'
import { paperFileUrl, PaperMergedError } from '@/services/api'
import { useNotes, usePaper } from '@/services/queries'
import { readerHref } from '@/router/route'
import { usePdfDocument } from '@/features/reader/usePdfDocument'

/** The paper, its PDF document and its notes, as the reader shows them. */
export function useReaderDocument(paperId: string) {
  const paper = usePaper(paperId)
  // Asked for once the paper says it has a PDF: one saved without asks for nothing and shows its details instead.
  // Details that failed to load say nothing either way, so the PDF is still tried.
  const mergedInto = paper.error instanceof PaperMergedError ? paper.error.keptId : null
  // A merged paper's id leads to the paper it became (R19); its own file, chunks and notes answer 410 too. The tab
  // and target in the query stay: M's chunks and notes moved to K with their ids.
  useEffect(() => {
    if (!mergedInto) return
    const query = window.location.hash.split('?')[1]
    window.location.replace(query ? `${readerHref(mergedInto)}?${query}` : readerHref(mergedInto))
  }, [mergedInto])
  const noPdf = paper.data?.has_pdf === false
  const { doc, error: pdfError } = usePdfDocument(paper.data?.has_pdf || (paper.isError && !mergedInto) ? paperFileUrl(paperId) : null)
  const notesQuery = useNotes(paperId)
  const notes = useMemo(() => notesQuery.data ?? [], [notesQuery.data])
  return { paper, noPdf, doc, pdfError, notesQuery, notes }
}
