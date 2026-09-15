/** What the connection dialog holds, and the request bodies it sends. */
export type ConnectionKind = 'ollama' | 'anthropic' | 'openai_compatible'
/** Editing: keep the stored key (nothing sent), replace it with `apiKey`, or remove it (null sent). */
export type KeyChange = 'keep' | 'replace' | 'remove'
export type ConnectionForm = { kind: ConnectionKind; label: string; baseUrl: string; apiKey: string; keyChange: KeyChange }

export const KIND_NAMES: Record<ConnectionKind, string> = {
  ollama: 'Ollama',
  anthropic: 'Anthropic',
  openai_compatible: 'OpenAI-compatible',
}

const baseUrlOf = (form: ConnectionForm) => (form.kind === 'anthropic' ? null : form.baseUrl.trim())

/** POST body. Anthropic has no address; Ollama has no key; an empty key field means no key. */
export function createBody(form: ConnectionForm) {
  const apiKey = form.kind === 'ollama' ? '' : form.apiKey.trim()
  return { kind: form.kind, label: form.label.trim(), base_url: baseUrlOf(form), api_key: apiKey || null }
}

/** PATCH body. The key goes only when it changes: a missing api_key keeps the stored one, null removes it. */
export function updateBody(form: ConnectionForm) {
  const body: { label: string; base_url: string | null; api_key?: string | null } = {
    label: form.label.trim(),
    base_url: baseUrlOf(form),
  }
  if (form.keyChange === 'replace' && form.apiKey.trim()) body.api_key = form.apiKey.trim()
  if (form.keyChange === 'remove') body.api_key = null
  return body
}
