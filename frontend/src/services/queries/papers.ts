import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { Paper, PaperUpdate } from '@/entities'
import { keys, PAPERS_POLL_MS } from './core'

/** Poll the library only while a paper is still ingesting. */
export function papersPollInterval(papers: Paper[] | undefined): number | false {
  return papers?.some((paper) => paper.status !== 'ready' && paper.status !== 'failed') ? PAPERS_POLL_MS : false
}

export const usePapers = () =>
  useQuery({
    queryKey: keys.papers,
    queryFn: api.listPapers,
    refetchInterval: (query) => papersPollInterval(query.state.data),
  })

export const usePaper = (id: string) =>
  useQuery({
    queryKey: keys.paper(id),
    queryFn: () => api.getPaper(id),
    // While it's ingesting, so the reader sees the moment it's ready.
    refetchInterval: (query) => (query.state.data ? papersPollInterval([query.state.data]) : false),
  })

/** One page's chunks, fetched only when `page` is set: the reader's `?chunk=` target needs its rects. */
export const useChunksOnPage = (paperId: string, page: number | null) =>
  useQuery({
    queryKey: keys.chunks(paperId, page ?? 0),
    queryFn: () => api.listChunks(paperId, page!),
    enabled: page !== null,
  })

/** Re-runs ingestion, which embeds the paper: the fix for papers ingested before chat existed. */
export function useReindexPaper(paperId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.reingestPaper(paperId),
    onSettled: () => client.invalidateQueries({ queryKey: keys.paper(paperId) }),
  })
}

/** Saves a manual correction. The reader shows the saved paper at once; the library refetches. */
export function useUpdatePaper(paperId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (update: PaperUpdate) => api.updatePaper(paperId, update),
    onSuccess: (paper) => {
      client.setQueryData(keys.paper(paperId), paper)
      return client.invalidateQueries({ queryKey: keys.papers, exact: true })
    },
  })
}

/** Uploads PDFs one by one; with a `workspaceId` (a workspace's Papers tab) each also joins that workspace. */
export function useUploadPapers(workspaceId?: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await api.uploadPaper(file, workspaceId)
    },
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.papers }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
      ]),
  })
}

export function useDeletePaper() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.deletePaper,
    // The paper drops out of any workspace it was in; refresh their counts and membership lists too.
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.papers }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
      ]),
  })
}

/** A paper saved without a PDF just got one: the paper, its workspaces' counts, PRISMA and hits (all under
 * keys.workspaces, which prefixes searchHitsRoot and prismaRoot of every workspace) refresh. */
function pdfArrived(client: QueryClient, paperId: string) {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.papers }),
    client.invalidateQueries({ queryKey: keys.paper(paperId) }),
    client.invalidateQueries({ queryKey: keys.workspaces }),
  ])
}

/** Got its PDF, here or (already_has_pdf) from another tab or request: either way the views catch up. */
const pdfArrivedOptions = (client: QueryClient, paperId: string) => ({
  onSuccess: () => pdfArrived(client, paperId),
  onError: (error: Error) => {
    if (error.message === 'already_has_pdf') void pdfArrived(client, paperId)
  },
})

export function useUploadPaperPdf(paperId: string) {
  const client = useQueryClient()
  return useMutation({ mutationFn: (file: File) => api.uploadPaperPdf(paperId, file), ...pdfArrivedOptions(client, paperId) })
}

export function useFindPaperPdf(paperId: string) {
  const client = useQueryClient()
  return useMutation({ mutationFn: () => api.findPaperPdf(paperId), ...pdfArrivedOptions(client, paperId) })
}

export const usePaperEvents = (paperId: string) =>
  useQuery({ queryKey: keys.paperEvents(paperId), queryFn: () => api.paperEvents(paperId) })

const FOUND_PDFS_POLL_MS = 60_000

/** Finds from the weekly re-check not yet dismissed; polled while the Library is open. */
export const useFoundPdfs = () =>
  useQuery({ queryKey: keys.foundPdfs, queryFn: api.foundPdfs, refetchInterval: FOUND_PDFS_POLL_MS })

export function useMarkFoundPdfsSeen() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => api.markFoundPdfsSeen(ids),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.foundPdfs }),
  })
}
