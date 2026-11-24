import { request, sendJson } from '../http'
import type { EvidenceCard, EvidenceCardRow, EvidenceChange } from '@/entities'

export const evidenceApi = {
  getEvidenceCard: (paperId: string) => request<EvidenceCard>(`/api/papers/${paperId}/evidence-card`),
  generateEvidenceCard: (paperId: string, regenerate: boolean, confirm: boolean) =>
    request<EvidenceCard[]>(`/api/papers/${paperId}/evidence-card`, sendJson('POST', { regenerate, confirm })),
  editEvidenceCard: (paperId: string, changes: EvidenceChange[]) =>
    request<EvidenceCard>(`/api/papers/${paperId}/evidence-card`, sendJson('PATCH', { changes })),
  listEvidenceCards: (workspaceId: string) =>
    request<EvidenceCardRow[]>(`/api/workspaces/${workspaceId}/evidence-cards`),
  generateEvidenceCards: (workspaceId: string) =>
    request<EvidenceCard[]>(`/api/workspaces/${workspaceId}/evidence-cards`, sendJson('POST', {})),
  evidenceCardsCsvUrl: (workspaceId: string) => `/api/workspaces/${workspaceId}/evidence-cards.csv`,
}
