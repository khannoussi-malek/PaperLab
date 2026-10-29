import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api, type SectionRoleIn } from '@/api/client'

// Every key starts with ['papers', paperId], like api/queries.ts's, so Re-index (`keys.paper(paperId)`) refreshes them.
const keys = {
  allChunks: (paperId: string) => ['papers', paperId, 'chunks', 'all'] as const,
  sections: (paperId: string) => ['papers', paperId, 'sections'] as const,
  briefs: (paperId: string) => ['papers', paperId, 'briefs'] as const,
}

/** Every section with its role, and every lens with its chunks (the lens picker, fading and the Lens tab). */
export const usePaperSections = (paperId: string, enabled = true) =>
  useQuery({ queryKey: keys.sections(paperId), queryFn: () => api.paperSections(paperId), enabled })

/** Warms the sections `usePaperSections` will ask for (the triage desk's next cards). */
export const prefetchPaperSections = (client: QueryClient, paperId: string) =>
  client.prefetchQuery({ queryKey: keys.sections(paperId), queryFn: () => api.paperSections(paperId) })

/** All of a paper's chunks, fetched only when `enabled`: a lens other than Full paper, or the Lens tab. */
export const usePaperChunks = (paperId: string, enabled: boolean) =>
  useQuery({ queryKey: keys.allChunks(paperId), queryFn: () => api.listAllChunks(paperId), enabled })

/** A role fix. The reply is the recomputed sections, shown at once; the briefs refetch to learn which went stale. */
export function useSetSectionRole(paperId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (change: SectionRoleIn) => api.setSectionRole(paperId, change),
    onSuccess: async (sections) => {
      // a sections fetch started before the fix would otherwise land after it and show the old roles
      await client.cancelQueries({ queryKey: keys.sections(paperId) })
      client.setQueryData(keys.sections(paperId), sections)
      return client.invalidateQueries({ queryKey: keys.briefs(paperId) })
    },
  })
}

/** The newest brief per lens, each saying whether it is out of date. */
export const usePaperBriefs = (paperId: string) =>
  useQuery({ queryKey: keys.briefs(paperId), queryFn: () => api.listBriefs(paperId) })

/** For the brief stream, which isn't a query: refetch the briefs once one is saved. */
export function useInvalidateBriefs(paperId: string) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.briefs(paperId) })
}
