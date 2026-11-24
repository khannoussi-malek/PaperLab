import { request, sendJson } from '../http'
import type { PackageImportResult, PackageRecordExists, Note, Paper, Workspace } from '@/entities'

export const notesZipUrl = (workspaceId: string) => `/api/workspaces/${encodeURIComponent(workspaceId)}/notes.zip`

/** The workspace as one `.paperlab` file; PDFs are in it only with `pdfs`. */
export const packageUrl = (workspaceId: string, pdfs: boolean, answers: boolean) =>
  `/api/workspaces/${encodeURIComponent(workspaceId)}/package?pdfs=${pdfs}&answers=${answers}`

/** The screening record an imported package carried, as JSON. */
export const packageRecordUrl = (workspaceId: string) =>
  `/api/workspaces/${encodeURIComponent(workspaceId)}/package-record`

/** Whether that record is kept, without downloading it. */
const packageRecordExistsUrl = (workspaceId: string) => `${packageRecordUrl(workspaceId)}/exists`

export const workspacesApi = {
  listWorkspaces: () => request<Workspace[]>('/api/workspaces'),
  /** A `.paperlab` file as a new workspace. A refusal is an ApiError whose code is a `package_*` one. */
  importPackage: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<PackageImportResult>('/api/workspaces/import-package', { method: 'POST', body: form })
  },
  /** Whether a workspace carries a screening record. */
  hasPackageRecord: (workspaceId: string) =>
    request<PackageRecordExists>(packageRecordExistsUrl(workspaceId)).then((body) => body.exists),
  /** Resolves when the package, with its PDFs when `pdfs` and its chat answers when `answers`, would export and import; a 409 ApiError when it is too large. */
  checkPackage: (workspaceId: string, pdfs: boolean, answers: boolean) =>
    request<void>(`/api/workspaces/${encodeURIComponent(workspaceId)}/package/check?pdfs=${pdfs}&answers=${answers}`),
  createWorkspace: (name: string) => request<Workspace>('/api/workspaces', sendJson('POST', { name })),
  renameWorkspace: (id: string, name: string) =>
    request<Workspace>(`/api/workspaces/${id}`, sendJson('PATCH', { name })),
  deleteWorkspace: (id: string) => request<void>(`/api/workspaces/${id}`, { method: 'DELETE' }),
  makeWorkspaceEditable: (id: string) => request<Workspace>(`/api/workspaces/${id}/make-editable`, { method: 'POST' }),
  listWorkspaceNotes: (id: string) => request<Note[]>(`/api/workspaces/${id}/notes`),
  listWorkspacePapers: (id: string) => request<Paper[]>(`/api/workspaces/${id}/papers`),
  addToWorkspace: (workspaceId: string, paperId: string) =>
    request<void>(`/api/workspaces/${workspaceId}/papers/${paperId}`, { method: 'PUT' }),
  removeFromWorkspace: (workspaceId: string, paperId: string) =>
    request<void>(`/api/workspaces/${workspaceId}/papers/${paperId}`, { method: 'DELETE' }),
}
