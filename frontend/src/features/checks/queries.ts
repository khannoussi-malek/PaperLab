import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'

// Starts with ['papers', paperId], like api/queries.ts's keys, so Re-index refreshes it; isNotesList matches 'checks'.
const checksKey = (paperId: string) => ['papers', paperId, 'checks'] as const

/** The newest check per note on a paper, each saying whether its note changed since. */
export const usePaperChecks = (paperId: string) =>
  useQuery({ queryKey: checksKey(paperId), queryFn: () => api.listChecks(paperId) })

/** For the check stream, which isn't a query: refetch the checks once one is saved. */
export function useInvalidateChecks(paperId: string) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: checksKey(paperId) })
}
