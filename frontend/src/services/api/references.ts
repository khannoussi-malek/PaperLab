import { request, sendJson } from '../http'
import type { Paper, ReferencePage, References, ReferencesDirection, RefreshOut } from '@/entities'

export const referencesApi = {
  /** One direction of a paper's references, ranked for this library. */
  references: (paperId: string, direction: ReferencesDirection) =>
    request<References>(`/api/papers/${paperId}/references?direction=${direction}`),
  /** Queues a fetch of both directions; a second call while already fetching is a no-op. */
  refreshReferences: (paperId: string) =>
    request<RefreshOut>(`/api/papers/${paperId}/references/refresh`, { method: 'POST' }),
  /** Downloads a reference's free PDF into the library; with a `workspaceId` it also joins that workspace. */
  importReference: (refId: string, workspaceId?: string) =>
    request<Paper>(`/api/references/${refId}/import`, sendJson('POST', { workspace_id: workspaceId ?? null })),
  /** The whole library's, or one workspace's, To read list and shared references (D121, D166). 404 unknown workspace. */
  referencePage: (workspaceId: string | null) =>
    request<ReferencePage>(workspaceId ? `/api/references?workspace=${workspaceId}` : '/api/references'),
  /** Marks a reference To read; a second call keeps the first time. 404 unknown reference. */
  queueReference: (refId: string) => request<{ queued_at: string | null }>(`/api/references/${refId}/queue`, sendJson('PUT', undefined)),
  /** Takes a reference off To read; harmless when it isn't on it. 404 unknown reference. */
  unqueueReference: (refId: string) => request<{ queued_at: string | null }>(`/api/references/${refId}/queue`, { method: 'DELETE' }),
}
