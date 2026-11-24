import { request, sendJson } from '../http'
import type { PaperTagGroup, TagDeleted, TagRenamed, TagResult, TagSummary } from '@/entities'

export const tagsApi = {
  listTags: (ws: string) => request<TagSummary[]>(`/api/workspaces/${ws}/tags`),
  paperTags: (ws: string) => request<Record<string, string[]>>(`/api/workspaces/${ws}/paper-tags`),
  tagsOfPaper: (paperId: string) => request<PaperTagGroup[]>(`/api/papers/${paperId}/tags`),
  applyTag: (ws: string, tag: string, paperIds: string[]) =>
    request<TagResult>(`/api/workspaces/${ws}/tags/apply`, sendJson('POST', { tag, paper_ids: paperIds })),
  removeTag: (ws: string, tag: string, paperIds: string[]) =>
    request<TagResult>(`/api/workspaces/${ws}/tags/remove`, sendJson('POST', { tag, paper_ids: paperIds })),
  renameTag: (ws: string, tagId: string, newName: string) =>
    request<TagRenamed>(`/api/workspaces/${ws}/tags/${tagId}`, sendJson('PATCH', { new_name: newName })),
  deleteTag: (ws: string, tagId: string) =>
    request<TagDeleted>(`/api/workspaces/${ws}/tags/${tagId}`, { method: 'DELETE' }),
}
