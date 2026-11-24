import { request, sendJson } from '../http'
import type { AvailableModels, ChatModel, ConnectionCheck, LLMConnection, LLMConnectionCreate, LLMConnectionUpdate, LLMModel, Skill, SkillCreate, SkillUpdate } from '@/entities'

export const llmApi = {
  listChatModels: () => request<ChatModel[]>('/api/llm/models'),
  /** `scope` narrows to the skills a chat of that kind can use; hidden ones come back only with `includeHidden`. */
  listSkills: (scope?: 'paper' | 'workspace', includeHidden?: boolean) => {
    const params = new URLSearchParams()
    if (scope) params.set('scope', scope)
    if (includeHidden) params.set('include_hidden', 'true')
    const query = params.toString()
    return request<Skill[]>(`/api/skills${query ? `?${query}` : ''}`)
  },
  createSkill: (body: SkillCreate) => request<Skill>('/api/skills', sendJson('POST', body)),
  updateSkill: (id: string, body: SkillUpdate) => request<Skill>(`/api/skills/${id}`, sendJson('PUT', body)),
  deleteSkill: (id: string) => request<void>(`/api/skills/${id}`, { method: 'DELETE' }),
  resetSkill: (id: string) => request<Skill>(`/api/skills/${id}/reset`, { method: 'POST' }),
  setSkillDefault: (id: string, scope: 'paper' | 'workspace', on: boolean) =>
    request<Skill>(`/api/skills/${id}/default`, sendJson('POST', { scope, on })),
  listConnections: () => request<LLMConnection[]>('/api/llm/connections'),
  createConnection: (body: LLMConnectionCreate) => request<LLMConnection>('/api/llm/connections', sendJson('POST', body)),
  updateConnection: (id: string, body: LLMConnectionUpdate) =>
    request<LLMConnection>(`/api/llm/connections/${id}`, sendJson('PATCH', body)),
  deleteConnection: (id: string) => request<void>(`/api/llm/connections/${id}`, { method: 'DELETE' }),
  testConnection: (id: string) => request<ConnectionCheck>(`/api/llm/connections/${id}/test`, { method: 'POST' }),
  availableModels: (id: string) => request<AvailableModels>(`/api/llm/connections/${id}/available`),
  addModel: (connectionId: string, name: string) =>
    request<LLMModel>(`/api/llm/connections/${connectionId}/models`, sendJson('POST', { name })),
  removeModel: (id: string) => request<void>(`/api/llm/models/${id}`, { method: 'DELETE' }),
  setDefaultModel: (modelId: string) => request<LLMModel>('/api/llm/default', sendJson('PUT', { model_id: modelId })),
  /** The raw response: on success its body is the pull's SSE stream (progress…, then done or error). `addToChat`
   * false: Settings → Search's pull, which never lists the model in chat (`done.model` is null). */
  pullModel: (connectionId: string, name: string, signal?: AbortSignal, addToChat = true) =>
    fetch(`/api/llm/connections/${connectionId}/pull`, { ...sendJson('POST', { name, add_to_chat: addToChat }), signal }),
  /** `name` goes in the query: Ollama names can contain `/`. */
  deleteInstalledModel: (connectionId: string, name: string) =>
    request<void>(`/api/llm/connections/${connectionId}/installed?name=${encodeURIComponent(name)}`, { method: 'DELETE' }),
}
