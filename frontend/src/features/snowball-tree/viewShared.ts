import type { ProvNode } from '@/api/client'
import type { BranchTarget } from './BranchControl'
import { isUnknown } from './layout'
import { decisionWord } from './levelText'

export type DecisionKey = 'relevant' | 'not_relevant' | 'none'
export const decisionKey = (n: ProvNode): DecisionKey => (n.decision === 'relevant' || n.decision === 'not_relevant' ? n.decision : 'none')

const BRANCH_WORD: Record<string, string> = { go_further: 'go further', stopped: 'stopped' }

/** The accessible name every view gives a paper, the same as the tree's boxes. */
export function paperLabel(n: ProvNode, title = n.title): string {
  const branch = n.branch ? BRANCH_WORD[n.branch.state] : undefined
  return `${title}, level ${n.level}, ${decisionWord(n.decision)}${branch ? `, ${branch}` : ''}`
}

/** What setBranch needs to name a paper, as in the side panel. Null for a "parent not recorded" box. */
export function branchTarget(n: ProvNode): BranchTarget | null {
  if (!n.id.startsWith('paper:') && !isUnknown(n.id)) return { hit_id: n.id }
  return n.paper_id ? { paper_id: n.paper_id } : null
}

/** SVG classes for a decision, from the same colour tokens as the tree's boxes. */
export const SVG_TONE: Record<DecisionKey | 'root', string> = {
  relevant: 'fill-included/20 stroke-included',
  not_relevant: 'fill-destructive/20 stroke-destructive',
  none: 'fill-muted stroke-border',
  root: 'fill-card stroke-foreground',
}
