import { request, sendJson } from '../http'
import type { LibraryGraph, PaperLinkOut } from '@/entities'

export const graphApi = {
  /** Every library paper and the links between them, or one workspace's. Capped at 2000 links. */
  libraryGraph: (workspaceId: string | null) =>
    request<LibraryGraph>(workspaceId ? `/api/graph?workspace=${workspaceId}` : '/api/graph'),
  createPaperLink: (fromPaper: string, toPaper: string, label: string) =>
    request<PaperLinkOut>('/api/links', sendJson('POST', { from_paper: fromPaper, to_paper: toPaper, label })),
  renamePaperLink: (id: string, label: string) =>
    request<PaperLinkOut>(`/api/links/${id}`, sendJson('PATCH', { label })),
  deletePaperLink: (id: string) => request<void>(`/api/links/${id}`, { method: 'DELETE' }),
}
