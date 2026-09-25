import type { ConnectionForm } from './connectionForm'

/** A place an OpenAI-compatible connection can point at. Chat POSTs `{baseUrl}/chat/completions`. */
export type Preset = { name: string; baseUrl: string }

// The API runs in Docker, so servers on this machine (LM Studio, Ollama) are reached through host.docker.internal.
export const PRESETS: Preset[] = [
  { name: 'OpenAI', baseUrl: 'https://api.openai.com/v1' },
  { name: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1' },
  { name: 'Groq', baseUrl: 'https://api.groq.com/openai/v1' },
  { name: 'Mistral', baseUrl: 'https://api.mistral.ai/v1' },
  { name: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1' },
  { name: 'Gemini', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  { name: 'LM Studio', baseUrl: 'http://host.docker.internal:1234/v1' },
  { name: 'Custom', baseUrl: '' },
]

export const OLLAMA_BASE_URL = 'http://host.docker.internal:11434'

/**
 * The dialog's name and address after picking a preset: its address, and its name unless the owner typed their own
 * (an empty name, or another preset's name, counts as not typed). Custom clears both.
 */
export function applyPreset(presetName: string, current: { label: string; baseUrl: string }) {
  const preset = PRESETS.find((p) => p.name === presetName) ?? PRESETS[PRESETS.length - 1]
  const typed = current.label.trim() !== '' && !PRESETS.some((p) => p.name === current.label.trim())
  const label = typed ? current.label : preset.name === 'Custom' ? '' : preset.name
  return { label, baseUrl: preset.baseUrl }
}

/** A new connection's form, from Settings → Search's "Add OpenAI key", "Add Gemini key" or "Add Ollama": Ollama at
 * its usual address, an OpenAI-compatible preset's name and address, or (no preset) an empty compatible form. */
export function presetForm(preset?: string): ConnectionForm {
  if (preset === 'Ollama') return { kind: 'ollama', label: 'Ollama', baseUrl: OLLAMA_BASE_URL, apiKey: '', keyChange: 'replace' }
  const empty: ConnectionForm = { kind: 'openai_compatible', label: '', baseUrl: '', apiKey: '', keyChange: 'replace' }
  return preset === undefined ? empty : { ...empty, ...applyPreset(preset, empty) }
}
