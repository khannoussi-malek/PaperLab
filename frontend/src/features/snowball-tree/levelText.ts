import type { LevelStats } from '@/api/client'

/** "Level 1 · 30 found · 4 already known · 6 included · 3 to go further · 1 stopped", plus " · done" or " · saturated". */
export function levelHeader(s: LevelStats): string {
  const base = `Level ${s.level} · ${s.found} found · ${s.already_known} already known · ${s.included} included · ${s.go_further} to go further · ${s.stopped} stopped`
  return s.done ? `${base} · done` : s.saturated ? `${base} · saturated` : base
}

/** Plain word for a hit's stage-1 decision; anything but relevant / not relevant is "not screened". */
export function decisionWord(decision: string | null | undefined): 'included' | 'excluded' | 'not screened' {
  return decision === 'relevant' ? 'included' : decision === 'not_relevant' ? 'excluded' : 'not screened'
}
