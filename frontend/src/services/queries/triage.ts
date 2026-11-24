import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { ReadingIn } from '@/entities'
import { keys } from './core'

/** The reader's own record of a paper (D118, D119): sets one field or both. Every notes list, workspace and the
 * graph can show it (the library chip, a workspace's Papers tab, the graph panel and tooltip). */
export function useSetReading() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ paperId, changes, source }: { paperId: string; changes: ReadingIn; source?: 'reader' | 'library' }) =>
      api.setReading(paperId, changes, source),
    onSuccess: (paper, { paperId }) => {
      client.setQueryData(keys.paper(paperId), paper)
      return Promise.all([
        client.invalidateQueries({ queryKey: keys.papers, exact: true }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
        client.invalidateQueries({ queryKey: keys.graph }),
        client.invalidateQueries({ queryKey: keys.triageEvents(paperId) }),
      ])
    },
  })
}

/** A desk session's counts; `enabled` keeps it quiet until the summary is shown. */
export const useTriageSummary = (sessionId: string, enabled: boolean) =>
  useQuery({ queryKey: ['triage-summary', sessionId] as const, queryFn: () => api.triageSummary(sessionId), enabled })

/** A paper's reading history; `enabled` keeps a closed popover from fetching. */
export const useTriageEvents = (paperId: string, enabled: boolean) =>
  useQuery({ queryKey: keys.triageEvents(paperId), queryFn: () => api.triageEvents(paperId), enabled })
