import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { EmbeddingStatus, PaperSourcesUpdate, SearchSourceIn } from '@/entities'
import { keys, PAPERS_POLL_MS } from './core'

/** GET /api/embedding again every 2 s while search is being rebuilt (D156), so every rebuild line moves; never else. */
export function embeddingPollInterval(status: Pick<EmbeddingStatus, 'rebuild'> | undefined): number | false {
  return status?.rebuild ? PAPERS_POLL_MS : false
}

export const useEmbeddingStatus = () =>
  useQuery({
    queryKey: keys.embedding,
    queryFn: api.embeddingStatus,
    refetchInterval: (query) => embeddingPollInterval(query.state.data),
  })

/** Whether the voice program is ready. Polls faster while it is still getting ready, then slowly: the chat's voice button reads it too. */
export const useVoiceStatus = () =>
  useQuery({
    queryKey: keys.voiceStatus,
    queryFn: api.voiceStatus,
    refetchOnMount: 'always',
    refetchInterval: (query) => {
      const stage = query.state.data?.stage
      return stage === 'downloading' || stage === 'loading' ? 2000 : 10000
    },
  })
export const useVoiceLatency = () => useQuery({ queryKey: keys.voiceLatency, queryFn: api.voiceLatency, refetchOnMount: 'always' })

/** For a stream that isn't a mutation (the search model's download): read the embedding status again. */
export function useInvalidateEmbedding() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.embedding })
}

export const usePaperSources = () => useQuery({ queryKey: keys.paperSources, queryFn: api.paperSources })

/** Saves a switch, a key or the contact email. Which sources answer changes, so searches and suggestions ask again. */
export function useUpdatePaperSources() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (patch: PaperSourcesUpdate) => api.updatePaperSources(patch),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.paperSources }),
        client.invalidateQueries({ queryKey: keys.discovery }),
      ]),
  })
}

/** The weekly re-check switch: it changes no search source, so only the sources view is refreshed. */
export function useUpdatePdfRecheck() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => api.updatePaperSources({ pdf_recheck_enabled: enabled }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.paperSources }),
  })
}

export function useSetHybridSearch() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => api.setHybridSearch(enabled),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.embedding }),
  })
}

/** Queues a re-embed of every paper; the status line refetches once it's queued. */
export function useReindexLibrary() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.reindexLibrary(false),
    onSettled: () => client.invalidateQueries({ queryKey: keys.embedding }),
  })
}

/** Settings' Try again (D155): resumes the rebuild for the papers not yet on the active source. Never asks first. */
export function useTryAgain() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.reindexLibrary(true),
    onSettled: () => client.invalidateQueries({ queryKey: keys.embedding }),
  })
}

/** Switches the search source (D158). The status refetches, and then polls while the rebuild runs. */
export function useSwitchSearchSource() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: SearchSourceIn) => api.switchSearchSource(body),
    onSettled: () => client.invalidateQueries({ queryKey: keys.embedding }),
  })
}

/** The folder Connect Claude prefills. */
export const useMcpSetup = () => useQuery({ queryKey: keys.mcpSetup, queryFn: api.mcpSetup })

/** Connect Claude's server check. Nothing is cached: each click checks again. */
export const useCheckMcpServer = () => useMutation({ mutationFn: api.checkMcpServer })

/** Connect Claude's activity list refreshes while the page is open, so a call made meanwhile shows up. */
export const MCP_ACTIVITY_POLL_MS = 10_000
export const useMcpActivity = () =>
  useQuery({ queryKey: keys.mcpActivity, queryFn: api.mcpActivity, refetchInterval: MCP_ACTIVITY_POLL_MS })

export const useClearMcpActivity = () => {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.clearMcpActivity,
    onSuccess: () => client.invalidateQueries({ queryKey: keys.mcpActivity }),
  })
}

export const useMcpSettings = () => useQuery({ queryKey: keys.mcpSettings, queryFn: api.mcpSettings })

/** The owner's switch for changes from Claude. The answer replaces the cached setting at once. */
export const useSetMcpWrites = () => {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.setMcpWrites,
    onSuccess: (settings) => client.setQueryData(keys.mcpSettings, settings),
  })
}

/** Whether the first-run setup is done (the server's one flag); read once on start (useOpenSetupOnStart). */
export const useSetup = () => useQuery({ queryKey: keys.setup, queryFn: api.setup })

/** Finish and Skip: done for every browser and the desktop app, since the flag lives on the server. */
export function useFinishSetup() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.setSetupDone(true),
    onSuccess: (setup) => client.setQueryData(keys.setup, setup),
  })
}
