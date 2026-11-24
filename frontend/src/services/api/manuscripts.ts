import { request, sendJson } from '../http'
import type { CheckInfo, CheckRunResult, CitablePaper, Diagram, DiagramStart, DoiCheckResult, DraftReview, DraftReviewEstimate, EvidenceFound, EvidenceRow, Manuscript, ManuscriptCreate, ManuscriptDetail, ManuscriptFile, ManuscriptFileText, ManuscriptImport, ManuscriptPatch, ManuscriptSnapshot, ManuscriptTemplate, MissingKey, ReportingGuideline, ReviewAllStart, ReviewEstimate, ReviewRun, ReviewSentence, ReviewStart, ReviewState, SectionReview, SectionReviewStart, SectionSpan } from '@/entities'
import type { components } from '@/entities/schema'

const manuscriptPath = (path: string) => path.split('/').map(encodeURIComponent).join('/')

export const manuscriptsApi = {
  listManuscripts: (workspaceId: string | null) =>
    request<Manuscript[]>(workspaceId ? `/api/workspaces/${workspaceId}/manuscripts` : '/api/manuscripts?orphans=true'),
  listManuscriptTemplates: () => request<ManuscriptTemplate[]>('/api/templates/manuscripts'),
  listReportingGuidelines: () => request<ReportingGuideline[]>('/api/reporting-guidelines'),
  getManuscript: (id: string) => request<ManuscriptDetail>(`/api/manuscripts/${id}`),
  createManuscript: (body: ManuscriptCreate) => request<ManuscriptDetail>('/api/manuscripts', sendJson('POST', body)),
  /** An Overleaf zip as a new manuscript; `skipped` names the members PaperLab can't hold. */
  importManuscript: (file: File, workspaceId?: string | null) => {
    const form = new FormData()
    form.append('file', file)
    if (workspaceId) form.append('workspace_id', workspaceId)
    return request<ManuscriptImport>('/api/manuscripts/import', { method: 'POST', body: form })
  },
  updateManuscript: (id: string, patch: ManuscriptPatch) =>
    request<ManuscriptDetail>(`/api/manuscripts/${id}`, sendJson('PATCH', patch)),
  deleteManuscript: (id: string) => request<void>(`/api/manuscripts/${id}`, { method: 'DELETE' }),
  getManuscriptFile: (id: string, path: string) =>
    request<ManuscriptFileText>(`/api/manuscripts/${id}/files/${manuscriptPath(path)}`),
  /** A figure or a text file from the computer, at `path` (a binary overwrites; a text file must be new). */
  uploadManuscriptFile: (id: string, path: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    form.append('path', path)
    return request<ManuscriptFile>(`/api/manuscripts/${id}/uploads`, { method: 'POST', body: form })
  },
  renameManuscriptFile: (id: string, path: string, newPath: string) =>
    request<ManuscriptFile>(`/api/manuscripts/${id}/files/${manuscriptPath(path)}/rename`, sendJson('POST', { new_path: newPath })),
  deleteManuscriptFile: (id: string, path: string) =>
    request<void>(`/api/manuscripts/${id}/files/${manuscriptPath(path)}`, { method: 'DELETE' }),
  manuscriptPapers: (id: string) => request<CitablePaper[]>(`/api/manuscripts/${id}/papers`),
  missingKeys: (id: string) => request<MissingKey[]>(`/api/manuscripts/${id}/missing-keys`),
  listManuscriptChecks: (id: string) => request<CheckInfo[]>(`/api/manuscripts/${id}/checks`),
  runChecks: (id: string, body: { names?: string[]; cost?: 'cheap' | 'full' }) =>
    request<CheckRunResult>(`/api/manuscripts/${id}/checks/run`, sendJson('POST', body)),
  runDoiCheck: (id: string) => request<DoiCheckResult>(`/api/manuscripts/${id}/checks/dois`, { method: 'POST' }),
  startReview: (id: string, body: ReviewStart) =>
    request<ReviewRun>(`/api/manuscripts/${id}/review`, sendJson('POST', body)),
  reviewEstimate: (id: string, includeUncited = true) =>
    request<ReviewEstimate>(`/api/manuscripts/${id}/review/all/estimate?include_uncited=${includeUncited}`),
  startReviewAll: (id: string, body: ReviewAllStart) =>
    request<ReviewRun>(`/api/manuscripts/${id}/review/all`, sendJson('POST', body)),
  reviewReportHref: (id: string) => `/api/manuscripts/${id}/review/report.md`,
  reviewState: (id: string, file: string) =>
    request<ReviewState>(`/api/manuscripts/${id}/review?file=${encodeURIComponent(file)}`),
  cancelReview: (id: string, runId: string) =>
    request<ReviewRun>(`/api/manuscripts/${id}/review/${runId}/cancel`, { method: 'POST' }),
  locateSentences: (id: string, text: string) =>
    request<{ sentences: ReviewSentence[] }>(`/api/manuscripts/${id}/review/locate`, sendJson('POST', { text })),
  dismissClaim: (id: string, hash: string) =>
    request<void>(`/api/manuscripts/${id}/review/dismissals/${hash}`, { method: 'PUT' }),
  restoreClaim: (id: string, hash: string) =>
    request<void>(`/api/manuscripts/${id}/review/dismissals/${hash}`, { method: 'DELETE' }),
  startSectionReview: (id: string, body: SectionReviewStart) =>
    request<SectionReview>(`/api/manuscripts/${id}/section-review`, sendJson('POST', body)),
  sectionReviews: (id: string, file: string) =>
    request<{ reviews: SectionReview[] }>(`/api/manuscripts/${id}/section-review?file=${encodeURIComponent(file)}`),
  cancelSectionReview: (id: string, reviewId: string) =>
    request<SectionReview>(`/api/manuscripts/${id}/section-review/${reviewId}/cancel`, { method: 'POST' }),
  startDraftReview: (id: string, body: components['schemas']['DraftReviewIn']) =>
    request<DraftReview>(`/api/manuscripts/${id}/draft-review`, sendJson('POST', body)),
  draftReview: (id: string) => request<{ review: DraftReview | null }>(`/api/manuscripts/${id}/draft-review`),
  draftReviewEstimate: (id: string) => request<DraftReviewEstimate>(`/api/manuscripts/${id}/draft-review/estimate`),
  cancelDraftReview: (id: string, reviewId: string) =>
    request<DraftReview>(`/api/manuscripts/${id}/draft-review/${reviewId}/cancel`, { method: 'POST' }),
  createDiagram: (id: string, body: DiagramStart) =>
    request<Diagram>(`/api/manuscripts/${id}/diagrams`, sendJson('POST', body)),
  diagram: (id: string, diagramId: string) => request<Diagram>(`/api/manuscripts/${id}/diagrams/${diagramId}`),
  setDiagramCode: (id: string, diagramId: string, code: string) =>
    request<Diagram>(`/api/manuscripts/${id}/diagrams/${diagramId}/code`, sendJson('PUT', { code })),
  cancelDiagram: (id: string, diagramId: string) =>
    request<Diagram>(`/api/manuscripts/${id}/diagrams/${diagramId}/cancel`, { method: 'POST' }),
  deleteDiagram: (id: string, diagramId: string) =>
    request<void>(`/api/manuscripts/${id}/diagrams/${diagramId}`, { method: 'DELETE' }),
  /** `stamp` (the row's updated_at) is in the URL so a new preview is a new URL and pdf.js fetches it again. */
  manuscriptDiagramPdfUrl: (id: string, diagramId: string, stamp: string) =>
    `/api/manuscripts/${id}/diagrams/${diagramId}/pdf?v=${encodeURIComponent(stamp)}`,
  locateSections: (id: string, file: string, text: string) =>
    request<{ sections: SectionSpan[] }>(`/api/manuscripts/${id}/section-review/locate`, sendJson('POST', { file, text })),
  pinPaper: (id: string, paperId: string) => request<{ key: string }>(`/api/manuscripts/${id}/papers/${paperId}/pin`, { method: 'POST' }),
  rankPapers: (id: string, text: string) =>
    request<{ paper_ids: string[] }>(`/api/manuscripts/${id}/papers/rank`, sendJson('POST', { text })),
  findEvidence: (id: string, sentence: string, confirmRemote = false) =>
    request<EvidenceFound>(`/api/manuscripts/${id}/evidence`, sendJson('POST', { sentence, confirm_remote: confirmRemote })),
  evidenceRows: (id: string, hash: string) => request<EvidenceRow[]>(`/api/manuscripts/${id}/evidence/${hash}`),
  addSection: (id: string, title: string, after: string | null) =>
    request<{ path: string }>(`/api/manuscripts/${id}/sections`, sendJson('POST', { title, after })),
  splitSections: (id: string) => request<{ paths: string[] }>(`/api/manuscripts/${id}/sections/split`, { method: 'POST' }),
  retitleSection: (id: string, path: string, title: string) =>
    request<{ path: string }>(`/api/manuscripts/${id}/sections/${manuscriptPath(path)}/retitle`, sendJson('POST', { title })),
  moveSection: (id: string, path: string, to: number) =>
    request<void>(`/api/manuscripts/${id}/sections/${manuscriptPath(path)}/move`, sendJson('POST', { to })),
  deleteSection: (id: string, path: string) =>
    request<void>(`/api/manuscripts/${id}/sections/${manuscriptPath(path)}`, { method: 'DELETE' }),
  /** `base` is the updated_at the editor last saw; null for a new file. A stale one is a 409 ApiError (file_changed). */
  saveManuscriptFile: (id: string, path: string, text: string, base: string | null) =>
    request<ManuscriptFile>(`/api/manuscripts/${id}/files/${manuscriptPath(path)}`, sendJson('PUT', { text, base_updated_at: base })),
  compileManuscript: (id: string) => request<{ state: string }>(`/api/manuscripts/${id}/compile`, { method: 'POST' }),
  /** `compiledAt` is in the URL so a new compile is a new URL and pdf.js fetches it again. */
  manuscriptPdfUrl: (id: string, compiledAt?: string | null) =>
    `/api/manuscripts/${id}/pdf${compiledAt ? `?v=${encodeURIComponent(compiledAt)}` : ''}`,
  /** Where a source line lands in the PDF. Rejects 404 no_sync when there is no index or no match. */
  syncForward: (id: string, file: string, line: number) =>
    request<{ page: number; x: number; y: number }>(
      `/api/manuscripts/${id}/synctex/forward?file=${encodeURIComponent(file)}&line=${line}`),
  /** Which source line a PDF spot comes from (page 1-based, x/y in points from the top-left). 404 no_sync too. */
  syncInverse: (id: string, page: number, x: number, y: number) =>
    request<{ file: string; line: number }>(`/api/manuscripts/${id}/synctex/inverse?page=${page}&x=${x}&y=${y}`),
  /** `pdf: false`: the LaTeX source and paperlab.bib alone, without the compiled PDF. */
  manuscriptExportUrl: (id: string, { pdf = true }: { pdf?: boolean } = {}) =>
    `/api/manuscripts/${id}/export.zip${pdf ? '' : '?pdf=false'}`,
  listManuscriptSnapshots: (id: string) => request<ManuscriptSnapshot[]>(`/api/manuscripts/${id}/snapshots`),
  restoreManuscriptSnapshot: (id: string, snapshotId: string) =>
    request<void>(`/api/manuscripts/${id}/snapshots/${snapshotId}/restore`, { method: 'POST' }),
}
