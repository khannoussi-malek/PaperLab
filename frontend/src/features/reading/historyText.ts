import type { TriageEvent } from '@/api/client'
import { readingChip, type Triage } from './passes'

const PILES: Record<string, string> = {
  read_closely: 'Read closely',
  skim: 'Skim',
  later: 'Later',
  not_relevant: 'Dropped',
  skip: 'Skipped',
}
const WHERE: Record<string, string> = {
  desk: 'from the desk',
  reader: 'from the reader',
  library: 'from the library menu',
  undo: 'by undoing',
}
const REASON_WORDS: Record<string, string> = { needs_background: 'needs background first' }
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const UNDECIDED = 'Undecided'

const two = (n: number) => String(n).padStart(2, '0')
const when = (iso: string) => {
  const d = new Date(iso)
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${two(d.getHours())}:${two(d.getMinutes())}`
}
const state = (pass: number, triage: string | null) => readingChip(pass, triage as Triage | null) ?? UNDECIDED

/** One history row in words: when, what changed, why (reason and PDF use), and where it came from. */
export function describeEvent(e: TriageEvent): { when: string; what: string; why: string | null; where: string } {
  const change = `${state(e.before_pass, e.before_triage)} → ${state(e.after_pass, e.after_triage)}`
  const what = e.source === 'undo' ? `Undone: ${change}` : e.pile ? (PILES[e.pile] ?? e.pile) : change
  const pdf = e.pdf_opened ? `PDF opened${e.pdf_ms && e.pdf_ms > 0 ? `, ${Math.max(1, Math.round(e.pdf_ms / 60000))} min` : ''}` : null
  const reason = e.reason ? (REASON_WORDS[e.reason] ?? e.reason.replaceAll('_', ' ')) : null
  return { when: when(e.created_at), what, why: [reason, pdf].filter(Boolean).join(' · ') || null, where: WHERE[e.source] ?? e.source }
}
