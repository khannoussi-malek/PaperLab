import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type NoteCreate, type NoteUpdate, type Paper, type PaperUpdate, type PromoteRequest } from './client'

export const PAPERS_POLL_MS = 2000

export const queryClient = new QueryClient({
  // A local API answers or fails at once; retrying a 404 only delays the error the user needs to see.
  defaultOptions: { queries: { retry: false } },
})

const keys = {
  papers: ['papers'] as const,
  paper: (id: string) => ['papers', id] as const,
  notes: (paperId: string) => ['papers', paperId, 'notes'] as const,
  chat: (paperId: string) => ['papers', paperId, 'chat'] as const,
}

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

export const usePaper = (id: string) => useQuery({ queryKey: keys.paper(id), queryFn: () => api.getPaper(id) })

export const useNotes = (paperId: string) =>
  useQuery({ queryKey: keys.notes(paperId), queryFn: () => api.listNotes(paperId) })

/** Saved questions and answers for a paper, oldest first. */
export const useChatHistory = (paperId: string) =>
  useQuery({ queryKey: keys.chat(paperId), queryFn: () => api.listChat(paperId) })

/** For the chat stream, which isn't a query: refetch the history once an answer is saved. */
export function useInvalidateChatHistory(paperId: string) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.chat(paperId) })
}

/** Re-runs ingestion, which embeds the paper: the fix for papers ingested before chat existed. */
export function useReindexPaper(paperId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.reingestPaper(paperId),
    onSettled: () => client.invalidateQueries({ queryKey: keys.paper(paperId) }),
  })
}

/** Saves part of a chat answer as an AI note. Resolves once the notes list has refetched and includes it. */
export function usePromoteNote(paperId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (promote: PromoteRequest) => api.promoteNote(promote),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.notes(paperId) }),
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

export function useUploadPapers() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await api.uploadPaper(file)
    },
    onSettled: () => client.invalidateQueries({ queryKey: keys.papers }),
  })
}

export function useDeletePaper() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.deletePaper,
    onSettled: () => client.invalidateQueries({ queryKey: keys.papers }),
  })
}

export function useNoteMutations(paperId: string) {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.notes(paperId) })
  return {
    create: useMutation({ mutationFn: (note: NoteCreate) => api.createNote(note), onSuccess }),
    update: useMutation({
      mutationFn: ({ id, ...patch }: { id: string } & NoteUpdate) => api.updateNote(id, patch),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.deleteNote, onSuccess }),
  }
}
