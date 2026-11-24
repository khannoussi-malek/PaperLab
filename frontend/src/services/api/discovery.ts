import { request, sendJson } from '../http'
import type { Candidate, NoveltyResult, Paper, SearchResult } from '@/entities'

export const discoveryApi = {
  novelty: (text: string) => request<NoveltyResult>('/api/novelty', sendJson('POST', { text })),
  /** Papers outside the library for a title, DOI, arXiv ID or OpenAlex ID, and a notice per source that failed. */
  searchPapers: (query: string) => request<SearchResult>(`/api/discovery/search?q=${encodeURIComponent(query)}`),
  similarPapers: (paperId: string) => request<Candidate[]>(`/api/papers/${paperId}/similar`),
  /** Downloads a found paper's free PDF into the library (or, with `saveWithoutPdf`, saves it without one); with a `workspaceId` it also joins that workspace. */
  addCandidate: (candidate: Candidate, workspaceId?: string, saveWithoutPdf = false) =>
    request<Paper>(
      '/api/discovery/add',
      sendJson('POST', { candidate, workspace_id: workspaceId ?? null, save_without_pdf: saveWithoutPdf }),
    ),
}
