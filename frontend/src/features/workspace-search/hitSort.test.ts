import { describe, expect, it } from 'vitest'
import { loadHitSort, saveHitSort } from './hitSort'

const memory = () => {
  const data = new Map<string, string>()
  return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) }
}

describe('hit sort choice', () => {
  it('defaults to found order and remembers a choice per workspace', () => {
    const storage = memory()
    expect(loadHitSort(storage, 'w1')).toBe('found')
    saveHitSort(storage, 'w1', 'ranked')
    expect(loadHitSort(storage, 'w1')).toBe('ranked')
    expect(loadHitSort(storage, 'w2')).toBe('found')
  })

  it('survives storage that throws or holds junk', () => {
    const throwing = { getItem: () => { throw new Error('blocked') }, setItem: () => { throw new Error('blocked') } }
    expect(loadHitSort(throwing, 'w1')).toBe('found')
    expect(() => saveHitSort(throwing, 'w1', 'ranked')).not.toThrow()
    const junk = { getItem: () => 'sideways', setItem: () => {} }
    expect(loadHitSort(junk, 'w1')).toBe('found')
    expect(loadHitSort(null, 'w1')).toBe('found')
  })
})
