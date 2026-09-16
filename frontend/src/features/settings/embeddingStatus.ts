import type { EmbeddingStatus } from '@/api/client'

const chunksText = (n: number) => `${n.toLocaleString('en-US')} ${n === 1 ? 'chunk' : 'chunks'}`

/** "indexed with nomic-ai/nomic-embed-text-v1.5 · 12,400 chunks", or null while nothing is indexed (not locked yet). */
export function indexedLine(status: EmbeddingStatus): string | null {
  if (status.chunks === 0) return null
  return `indexed with ${status.indexed_with.map((i) => i.model).join(', ')} · ${chunksText(status.chunks)}`
}

/** Chunks whose vectors came from another model than the one the app now embeds with: chat on them is refused. */
export function staleChunks(status: EmbeddingStatus): number {
  return status.indexed_with.filter((i) => i.model !== status.model).reduce((sum, i) => sum + i.chunks, 0)
}
