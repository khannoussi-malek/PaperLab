import { request, sendJson } from '../http'
import type { EmbeddingStatus, McpActivity, McpCheck, McpSettings, McpSetup, PaperSources, PaperSourcesUpdate, SearchSourceIn, SetupState, VoiceLatency, VoiceStatus } from '@/entities'

export const settingsApi = {
  embeddingStatus: () => request<EmbeddingStatus>('/api/embedding'),
  voiceStatus: () => request<VoiceStatus>('/api/voice/status'),
  voiceLatency: () => request<VoiceLatency>('/api/voice/latency'),
  /** The raw response: on success its body is the download's SSE stream (progress…, then done or error). */
  downloadSearchModel: () => fetch('/api/embedding/model', { method: 'POST' }),
  setHybridSearch: (enabled: boolean) =>
    request<{ hybrid_search: boolean }>('/api/embedding/hybrid', sendJson('PUT', { enabled })),
  /** `missingOnly`: Settings' Try again, which embeds only the papers not yet on the active source. */
  reindexLibrary: (missingOnly: boolean) =>
    request<{ papers: number }>('/api/embedding/reindex', sendJson('POST', { confirm: true, missing_only: missingOnly })),
  /** Probes the source, then saves it and queues the papers not yet on it: 202 {papers}, 200 for the source in use. */
  switchSearchSource: (body: SearchSourceIn) =>
    request<{ papers: number }>('/api/embedding/source', sendJson('PUT', body)),
  paperSources: () => request<PaperSources>('/api/paper-sources'),
  /** Only what `patch` holds changes: a key left out is kept, a null key is removed. */
  updatePaperSources: (patch: PaperSourcesUpdate) =>
    request<PaperSources>('/api/paper-sources', sendJson('PATCH', patch)),
  /** The folder `docker compose up` ran in, to prefill Connect Claude; null outside Compose. */
  mcpSetup: () => request<McpSetup>('/api/mcp/setup'),
  /** Starts the MCP server as a client would and reads the library through it. Takes up to 30 s. */
  checkMcpServer: () => request<McpCheck>('/api/mcp/check', { method: 'POST' }),
  /** The newest tool calls MCP clients made on the library (1-500 rows), newest first. */
  mcpActivity: () => request<McpActivity[]>('/api/mcp/activity'),
  /** Empties the activity list. */
  clearMcpActivity: () => request<void>('/api/mcp/activity', { method: 'DELETE' }),
  /** Whether Claude may change the library (add, tag, write, delete). On by default. */
  mcpSettings: () => request<McpSettings>('/api/mcp/settings'),
  setMcpWrites: (writesEnabled: boolean) => request<McpSettings>('/api/mcp/settings', sendJson('PUT', { writes_enabled: writesEnabled })),
  /** Whether the first-run setup is done: while it isn't, the app opens #/setup on start. */
  setup: () => request<SetupState>('/api/setup'),
  /** Finish and Skip send true; false is for tests. */
  setSetupDone: (done: boolean) => request<SetupState>('/api/setup', sendJson('PUT', { done })),
}
