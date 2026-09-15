import { describe, expect, it } from 'vitest'
import { applyPreset, PRESETS } from './presets'

const blank = { label: '', baseUrl: '' }

describe('applyPreset', () => {
  it.each([
    ['OpenAI', 'https://api.openai.com/v1'],
    ['OpenRouter', 'https://openrouter.ai/api/v1'],
    ['Groq', 'https://api.groq.com/openai/v1'],
    ['Mistral', 'https://api.mistral.ai/v1'],
    ['DeepSeek', 'https://api.deepseek.com/v1'],
    ['Gemini', 'https://generativelanguage.googleapis.com/v1beta/openai'],
    ['LM Studio', 'http://host.docker.internal:1234/v1'],
  ])('%s fills its base URL and names the connection after it', (name, baseUrl) => {
    expect(applyPreset(name, blank)).toEqual({ label: name, baseUrl })
  })

  it('lists exactly the presets above, then Custom', () => {
    expect(PRESETS.map((p) => p.name)).toEqual(['OpenAI', 'OpenRouter', 'Groq', 'Mistral', 'DeepSeek', 'Gemini', 'LM Studio', 'Custom'])
  })

  it('Custom clears the address and a preset name, so the owner types both', () => {
    expect(applyPreset('Custom', { label: 'Groq', baseUrl: 'https://api.groq.com/openai/v1' })).toEqual(blank)
  })

  it("keeps a name the owner typed, and replaces another preset's name", () => {
    expect(applyPreset('Groq', { label: 'My Groq', baseUrl: '' })).toEqual({ label: 'My Groq', baseUrl: 'https://api.groq.com/openai/v1' })
    expect(applyPreset('Groq', { label: 'OpenAI', baseUrl: 'https://api.openai.com/v1' }).label).toBe('Groq')
  })
})
