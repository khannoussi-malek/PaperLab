import { describe, expect, it } from 'vitest'
import { createBody, updateBody, type ConnectionForm } from './connectionForm'

const form = (fields: Partial<ConnectionForm>): ConnectionForm => ({
  kind: 'openai_compatible',
  label: ' OpenRouter ',
  baseUrl: ' https://openrouter.ai/api/v1 ',
  apiKey: ' sk-or-1234 ',
  keyChange: 'keep',
  ...fields,
})

describe('createBody', () => {
  it('sends the trimmed fields, and no key as null', () => {
    expect(createBody(form({}))).toEqual({
      kind: 'openai_compatible',
      label: 'OpenRouter',
      base_url: 'https://openrouter.ai/api/v1',
      api_key: 'sk-or-1234',
    })
    expect(createBody(form({ apiKey: '  ' })).api_key).toBeNull()
  })

  it('gives Anthropic no address and Ollama no key, whatever the hidden fields still hold', () => {
    expect(createBody(form({ kind: 'anthropic' }))).toMatchObject({ base_url: null, api_key: 'sk-or-1234' })
    expect(createBody(form({ kind: 'ollama' }))).toMatchObject({ base_url: 'https://openrouter.ai/api/v1', api_key: null })
  })
})

describe('updateBody', () => {
  it('leaves the key out when it is kept, so the stored key stays', () => {
    expect(updateBody(form({ keyChange: 'keep' }))).toEqual({ label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1' })
    expect('api_key' in updateBody(form({ keyChange: 'replace', apiKey: ' ' }))).toBe(false)
  })

  it('sends a replacement key, or null to remove it', () => {
    expect(updateBody(form({ keyChange: 'replace', apiKey: ' sk-new ' })).api_key).toBe('sk-new')
    expect(updateBody(form({ keyChange: 'remove' })).api_key).toBeNull()
  })
})
