import { errorDetail, request, sendJson } from '../http'
import type { ImportPreview, ImportProgress } from '@/entities'

export const citationsUrl = (workspaceId: string, format: string) =>
  `/api/workspaces/${encodeURIComponent(workspaceId)}/citations?format=${format}`

/** BibTeX plus each paper's PDF and notes, as Zotero imports it. */
export const zoteroZipUrl = (workspaceId: string) =>
  `/api/workspaces/${encodeURIComponent(workspaceId)}/citations.zip?format=bibtex&notes=true`

export const citationsApi = {
  /** What importing `file` would do. Nothing is written. */
  /** With fetching on (the API's default): only `would_fetch` and `disclosure` depend on it, and none on the target. */
  previewImport: (file: File, saveWithoutPdf = true) => {
    const form = new FormData()
    form.append('file', file)
    form.append('save_without_pdf', String(saveWithoutPdf))
    return request<ImportPreview>('/api/citations/import/preview', { method: 'POST', body: form })
  },
  /** Starts an import: 200 gives the result now, 202 a job id to poll (same body shape either way). */
  startImport: (file: File, target: { workspaceId?: string; newWorkspaceName?: string }, fetchFreePdfs: boolean, saveWithoutPdf = true) => {
    const form = new FormData()
    form.append('file', file)
    if (target.workspaceId) form.append('workspace_id', target.workspaceId)
    if (target.newWorkspaceName) form.append('new_workspace_name', target.newWorkspaceName)
    form.append('fetch_free_pdfs', String(fetchFreePdfs))
    form.append('save_without_pdf', String(saveWithoutPdf))
    return request<ImportProgress>('/api/citations/import', { method: 'POST', body: form })
  },
  importProgress: (jobId: string) => request<ImportProgress>(`/api/citations/import/${encodeURIComponent(jobId)}`),
  /** The chosen papers as one citations file (with `workspaceId`, that workspace's tags go in the keywords); resolves to its bytes and the server's file name. */
  exportSelection: async (paperIds: string[], format: 'bibtex' | 'ris', workspaceId?: string): Promise<{ blob: Blob; filename: string }> => {
    const response = await fetch('/api/citations/export', sendJson('POST', { paper_ids: paperIds, format, workspace_id: workspaceId }))
    if (!response.ok) throw new Error(await errorDetail(response))
    const name = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1]
    return { blob: await response.blob(), filename: name ?? `citations.${format === 'ris' ? 'ris' : 'bib'}` }
  },
  /** A workspace's citations as text (the apa-html preview and the plain apa to copy). Downloads use the URL directly. */
  citationsText: async (workspaceId: string, format: string): Promise<string> => {
    const response = await fetch(citationsUrl(workspaceId, format))
    if (!response.ok) throw new Error(await errorDetail(response))
    return response.text()
  },
}
