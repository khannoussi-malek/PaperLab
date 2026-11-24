import { request, sendJson } from '../http'
import type { Brief, Chunk, EmbeddingProgress, FoundPdf, LensId, Paper, PaperEvent, PaperSections, PaperUpdate, SectionRoleIn } from '@/entities'

export const paperFileUrl = (id: string) => `/api/papers/${id}/file`

export const papersApi = {
  listPapers: () => request<Paper[]>('/api/papers'),
  getPaper: (id: string) => request<Paper>(`/api/papers/${id}`),
  /** With a `workspaceId`, the new paper also joins that workspace. */
  uploadPaper: (file: File, workspaceId?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (workspaceId) form.append('workspace_id', workspaceId)
    return request<Paper>('/api/papers', { method: 'POST', body: form })
  },
  updatePaper: (id: string, update: PaperUpdate) => request<Paper>(`/api/papers/${id}`, sendJson('PATCH', update)),
  deletePaper: (id: string) => request<void>(`/api/papers/${id}`, { method: 'DELETE' }),
  /** Attaches `file` to a paper saved without a PDF; it then ingests. 409 already_has_pdf, 422 not_a_pdf / pdf_too_large. */
  uploadPaperPdf: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Paper>(`/api/papers/${id}/pdf`, { method: 'POST', body: form })
  },
  /** Looks for a free copy and attaches it. Rejects NoFreePdfError (what was tried), AlreadyInLibraryError, or already_has_pdf. */
  findPaperPdf: (id: string) => request<Paper>(`/api/papers/${id}/find-pdf`, { method: 'POST' }),
  reingestPaper: (id: string) => request<Paper>(`/api/papers/${id}/reingest`, { method: 'POST' }),
  embeddingProgress: (paperId: string) => request<EmbeddingProgress>(`/api/papers/${paperId}/embedding-progress`),
  listChunks: (paperId: string, page: number) => request<Chunk[]>(`/api/papers/${paperId}/chunks?page=${page}`),
  /** Every chunk of a paper, in reading order: the lens fades and jumps need their rects. */
  listAllChunks: (paperId: string) => request<Chunk[]>(`/api/papers/${paperId}/chunks`),
  /** Every section with its role, and every lens with its chunks. */
  paperSections: (paperId: string) => request<PaperSections>(`/api/papers/${paperId}/sections`),
  /** The reader's role for a heading (`role` null: back to the automatic one). Answers the sections again. */
  setSectionRole: (paperId: string, change: SectionRoleIn) =>
    request<PaperSections>(`/api/papers/${paperId}/section-roles`, sendJson('PUT', change)),
  listBriefs: (paperId: string) => request<Brief[]>(`/api/papers/${paperId}/briefs`),
  /** The raw response: on success its body is the brief's SSE stream, with chat's events. No body: `modelId` is the
   *  optional `?model_id=` query, and null asks the default. */
  generateBrief: (paperId: string, lens: LensId, modelId: string | null, signal?: AbortSignal) =>
    fetch(`/api/papers/${paperId}/briefs/${lens}${modelId ? `?model_id=${encodeURIComponent(modelId)}` : ''}`, {
      method: 'POST',
      signal,
    }),
  paperEvents: (paperId: string) => request<PaperEvent[]>(`/api/papers/${paperId}/events`),
  foundPdfs: () => request<FoundPdf[]>('/api/papers/found-pdfs'),
  markFoundPdfsSeen: (ids: string[]) => request<void>('/api/papers/found-pdfs/seen', sendJson('POST', { ids })),
}
