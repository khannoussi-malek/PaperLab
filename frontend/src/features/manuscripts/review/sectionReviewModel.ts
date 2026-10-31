import { Check, CircleDashed, TriangleAlert, type LucideIcon } from 'lucide-react'
import type { Role, SectionFinding, SectionRef, SectionReview, SectionSpan } from '@/api/client'
import type { Tone } from './reviewModel'

export { ROLE_LABEL } from '@/features/lenses/lenses'

/** The roles a section can be reviewed as, in reading order (back matter and "other" have no rubric). */
export const REVIEWABLE_ROLES: Role[] = ['abstract', 'intro', 'related', 'method', 'results', 'discussion', 'limitations', 'conclusion']

type Kind = SectionFinding['kind']
const KINDS: Kind[] = ['missing', 'unsupported', 'supported']
export const FINDING_LABEL: Record<Kind, string> = { missing: 'Missing', unsupported: 'Unsupported', supported: 'Supported' }
export const FINDING_ICON: Record<Kind, LucideIcon> = { missing: CircleDashed, unsupported: TriangleAlert, supported: Check }
const TONE: Record<Kind, Tone> = { missing: 'warn', unsupported: 'bad', supported: 'good' }
export const findingTone = (kind: Kind): Tone => TONE[kind]

/** The findings by kind, Missing first; empty groups left out. */
export const groupFindings = (review: Pick<SectionReview, 'findings'>) =>
  KINDS.map((kind) => ({ kind, findings: review.findings.filter((f) => f.kind === kind) })).filter((g) => g.findings.length > 0)

/** Reviews whose section no longer reads as it did (its hash is in no span), running ones included. */
export function staleReviews<R extends Pick<SectionReview, 'section_hash'>>(spans: Pick<SectionSpan, 'hash'>[], reviews: R[]): R[] {
  const hashes = new Set(spans.map((s) => s.hash))
  return reviews.filter((r) => !hashes.has(r.section_hash))
}

/** The section under the cursor, as the server picks it: start inclusive, end exclusive, the very end of the last counts. */
export function sectionAt<S extends Pick<SectionSpan, 'start' | 'end'>>(spans: S[], cursor: number): S | null {
  return spans.find((s) => s.start <= cursor && cursor < s.end) ?? spans.slice(-1).find((s) => cursor === s.end) ?? null
}

export const refChip = (ref: SectionRef): string =>
  ref.kind === 'sentence' ? `S${ref.n} · ${ref.preview ?? ''}…` : `Note · ${ref.note_id && ref.paper_id ? ref.label : 'note removed'}`
