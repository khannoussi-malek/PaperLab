import { describe, expect, it } from 'vitest'
import { CHAT_MODEL_KEY, loadChatModel, saveChatModel } from './chatModel'

const MODELS = [
  { id: 'default-id', is_default: true },
  { id: 'other-id', is_default: false },
]

const memoryStorage = (initial: Record<string, string> = {}) => {
  const data = new Map(Object.entries(initial))
  return { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => void data.set(key, value) }
}

const blockedStorage = {
  getItem: (): string | null => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
}

describe('loadChatModel / saveChatModel', () => {
  it('keeps the last pick while that model still exists', () => {
    const storage = memoryStorage()
    saveChatModel(storage, 'other-id')
    expect(storage.getItem(CHAT_MODEL_KEY)).toBe('other-id')
    expect(loadChatModel(storage, MODELS)).toBe('other-id')
  })

  it('falls back to the default when the picked model was removed, or storage holds junk', () => {
    expect(loadChatModel(memoryStorage({ [CHAT_MODEL_KEY]: 'removed-id' }), MODELS)).toBe('default-id')
    expect(loadChatModel(memoryStorage({ [CHAT_MODEL_KEY]: '{"not":"an id"}' }), MODELS)).toBe('default-id')
  })

  it('falls back to the default without storage, or when storage throws, and saving there does not throw', () => {
    expect(loadChatModel(undefined, MODELS)).toBe('default-id')
    expect(loadChatModel(blockedStorage, MODELS)).toBe('default-id')
    expect(() => saveChatModel(blockedStorage, 'other-id')).not.toThrow()
  })

  it('is null with no pick and no default, so the server answers no_model', () => {
    expect(loadChatModel(memoryStorage(), [{ id: 'other-id', is_default: false }])).toBeNull()
    expect(loadChatModel(memoryStorage(), [])).toBeNull()
  })
})
