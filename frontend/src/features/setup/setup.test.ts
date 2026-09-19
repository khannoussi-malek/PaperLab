import { describe, expect, it } from 'vitest'
import { CHAT_SUGGESTIONS, isLinux, listedModelId, openSetupOnStart, pullLabel, suggestedPulls } from './setup'

describe('openSetupOnStart', () => {
  it("opens the setup on start while the server says it isn't done, unless it is already open", () => {
    expect(openSetupOnStart(false, '#/')).toBe(true)
    expect(openSetupOnStart(false, '#/papers/1f0e7570-3249-4d59-aa5c-8f9a03c2b70a')).toBe(true)
    expect(openSetupOnStart(false, '#/setup')).toBe(false)
    expect(openSetupOnStart(true, '#/')).toBe(false)
  })
})

describe('the chat step', () => {
  it('offers the two chat models to pull, with their sizes, until Ollama has them', () => {
    expect(CHAT_SUGGESTIONS.map(pullLabel)).toEqual(['Pull qwen3:4b · 2.5 GB', 'Pull qwen3:8b · 5.2 GB'])
    expect(CHAT_SUGGESTIONS.map((suggestion) => suggestion.note)).toEqual(['For 8 GB of memory.', "PaperLab's default."])
    expect(suggestedPulls(['fake-large', 'qwen3:8b']).map((suggestion) => suggestion.name)).toEqual(['qwen3:4b'])
    expect(suggestedPulls(['qwen3:4b', 'qwen3:8b'])).toEqual([])
  })

  it("finds a model chat already lists, so picking it isn't added twice", () => {
    const connection = { models: [{ id: 'm1', name: 'qwen3:8b', is_default: true }] }

    expect(listedModelId(connection, 'qwen3:8b')).toBe('m1')
    expect(listedModelId(connection, 'qwen3:4b')).toBeNull()
  })

  it('tells Linux, where Ollama must listen beyond 127.0.0.1, from the other systems', () => {
    const linux = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) PaperLab/0.1.0 Chrome/140.0.0.0 Electron/44.4.3 Safari/537.36'
    const mac = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
    const android = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36'

    expect([isLinux(linux), isLinux(mac), isLinux(android)]).toEqual([true, false, false])
  })
})
