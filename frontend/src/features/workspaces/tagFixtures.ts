import type { TagSummary } from '@/api/client'

export const tagSummary = (name: string, papers: number, extra: Partial<TagSummary> = {}): TagSummary => ({
  id: `t-${name}`, name, papers, peer_reviewed: 0, preprint: 0, unknown_review: 0, full_text: 0, abstract: 0, metadata: 0, ...extra,
})
