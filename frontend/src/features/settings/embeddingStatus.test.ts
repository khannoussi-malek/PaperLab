import { describe, expect, it } from 'vitest'
import { indexedLine, staleChunks } from './embeddingStatus'

const NOMIC = 'nomic-ai/nomic-embed-text-v1.5'

describe('indexedLine', () => {
  it('names the model and counts the chunks', () => {
    expect(indexedLine({ model: NOMIC, chunks: 12400, indexed_with: [{ model: NOMIC, chunks: 12400 }] })).toBe(
      `indexed with ${NOMIC} · 12,400 chunks`,
    )
    expect(indexedLine({ model: NOMIC, chunks: 1, indexed_with: [{ model: NOMIC, chunks: 1 }] })).toBe(`indexed with ${NOMIC} · 1 chunk`)
  })

  it('is null while nothing is indexed', () => {
    expect(indexedLine({ model: NOMIC, chunks: 0, indexed_with: [] })).toBeNull()
  })

  it('names every model when the index mixes them', () => {
    const mixed = { model: 'BAAI/bge-base-en-v1.5', chunks: 30, indexed_with: [{ model: NOMIC, chunks: 20 }, { model: 'BAAI/bge-base-en-v1.5', chunks: 10 }] }
    expect(indexedLine(mixed)).toBe(`indexed with ${NOMIC}, BAAI/bge-base-en-v1.5 · 30 chunks`)
    expect(staleChunks(mixed)).toBe(20)
  })
})
