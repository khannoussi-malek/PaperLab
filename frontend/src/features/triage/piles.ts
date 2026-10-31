import type { TriageDecisionIn } from '@/api/client'

export type Pile = 'read_closely' | 'skim' | 'later' | 'not_relevant' | 'skip'
type Triage = 'keep' | 'later' | 'drop' | null

export const PILE_ORDER: readonly Pile[] = ['read_closely', 'skim', 'later', 'not_relevant', 'skip']

export const PILES: Record<
  Pile,
  { label: string; key: 1 | 2 | 3 | 4 | 5; arrow: 'ArrowRight' | 'ArrowDown' | 'ArrowUp' | 'ArrowLeft' | ' '; target: 'right' | 'down' | 'up' | 'left' | null }
> = {
  read_closely: { label: 'Read closely', key: 1, arrow: 'ArrowRight', target: 'right' },
  skim: { label: 'Skim', key: 2, arrow: 'ArrowDown', target: 'down' },
  later: { label: 'Later', key: 3, arrow: 'ArrowUp', target: 'up' },
  not_relevant: { label: 'Not relevant', key: 4, arrow: 'ArrowLeft', target: 'left' },
  skip: { label: 'Skip', key: 5, arrow: ' ', target: null },
}

const r = (key: string, label = key.replaceAll('_', ' ')) => ({ key, label })
/** Mirrors REASONS in backend/app/core/triage.py (a test compares them). */
export const REASONS: Record<Pile, readonly { key: string; label: string }[]> = {
  read_closely: [r('core_to_my_question', 'core to my question'), r('method_i_need', 'method I need'), r('key_background', 'key background')],
  skim: [r('background_only', 'background only'), r('related_work', 'related work'), r('partly_relevant', 'partly relevant')],
  later: [r('needs_background', 'needs background first'), r('maybe_relevant_later', 'maybe relevant later'), r('related_work', 'related work')],
  not_relevant: [r('off_topic', 'off-topic'), r('wrong_method', 'wrong method'), r('low_quality', 'low quality'), r('duplicate'), r('already_known', 'already known'), r('other')],
  skip: [],
}

export function pileForKey(key: string): Pile | null {
  return PILE_ORDER.find((p) => key === PILES[p].arrow || key === String(PILES[p].key)) ?? null
}

/** Dominant axis wins; a tie goes horizontal; under `min` px is no decision. */
export function pileForDrag(dx: number, dy: number, min = 80): Pile | null {
  if (Math.max(Math.abs(dx), Math.abs(dy)) < min) return null
  if (Math.abs(dx) >= Math.abs(dy)) return dx > 0 ? 'read_closely' : 'not_relevant'
  return dy > 0 ? 'skim' : 'later'
}

/** The backend's mapping, only to restore the card's display before the server answers. */
export function nextState(pile: Pile, triage: Triage, pass: number): { triage: Triage; pass: number } {
  switch (pile) {
    case 'read_closely': return { triage: 'keep', pass }
    case 'skim': return { triage: 'keep', pass: Math.max(pass, 1) }
    case 'later': return { triage: 'later', pass }
    case 'not_relevant': return { triage: 'drop', pass }
    case 'skip': return { triage, pass }
  }
}

export function buildDecision(a: {
  pile: Pile
  sessionId: string
  clientId: string
  reason?: string
  note?: string
  clock: { card_ms: number; pdf_ms: number; pdf_opened: boolean }
}): TriageDecisionIn {
  if (a.pile === 'not_relevant' && !a.reason) throw new Error('A not-relevant decision needs a reason')
  return {
    pile: a.pile,
    session_id: a.sessionId,
    client_id: a.clientId,
    ...(a.reason ? { reason: a.reason } : {}),
    ...(a.note ? { note: a.note } : {}),
    pdf_opened: a.clock.pdf_opened,
    pdf_ms: Math.round(a.clock.pdf_ms),
    card_ms: Math.round(a.clock.card_ms),
  }
}
