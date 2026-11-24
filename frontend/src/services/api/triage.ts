import { request, sendJson } from '../http'
import type { Paper, ReadingIn, TriageDecision, TriageDecisionIn, TriageEvent, TriageSummary } from '@/entities'

export const triageApi = {
  /** The reader's own record (D118, D119): passes finished, keep/later/drop, or both. A field left out keeps its
   * value. 422 for an out-of-range pass, an unknown decision, or an empty body. `source` names where the change came
   * from (`reader` is the server's default, `library` the row menu). */
  setReading: (id: string, changes: ReadingIn, source?: 'reader' | 'library') => {
    const init = sendJson('PUT', changes)
    return request<Paper>(`/api/papers/${id}/reading`, source ? { ...init, headers: { ...init.headers, 'X-PaperLab-Source': source } } : init)
  },
  triageEvents: async (id: string) => (await request<{ events: TriageEvent[] }>(`/api/papers/${id}/triage-events`)).events,
  decideTriage: (paperId: string, body: TriageDecisionIn) => request<TriageDecision>(`/api/papers/${paperId}/triage-decisions`, sendJson('POST', body)),
  addTriageReason: (eventId: string, reason: string) => request<TriageEvent>(`/api/triage-events/${eventId}`, sendJson('PATCH', { reason })),
  undoTriage: (eventId: string) => request<TriageDecision>(`/api/triage-events/${eventId}/undo`, { method: 'POST' }),
  triageSummary: (sessionId: string) => request<TriageSummary>(`/api/triage-summary?session_id=${encodeURIComponent(sessionId)}`),
}
