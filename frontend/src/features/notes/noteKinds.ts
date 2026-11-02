import type { Note, NoteKind } from '@/api/client'
import { PASSES } from '../reading/passes'

export const KIND_LABEL: Record<NoteKind, string> = {
  five_cs: 'Five Cs',
  summary: 'Summary',
  reconstruction: 'Reconstruction',
  assumption: 'Assumption',
  future_work: 'Future work',
  figure: 'Figure',
}

const FIGURE_QUESTIONS = [
  'Are the axes labelled?',
  'Is there an error bar or another measure of spread?',
  'Do the conclusions follow from it?',
].join('\n')

export const KIND_HINT: Record<NoteKind, string> = {
  five_cs: 'Answer each C in a line or two, from your first pass.',
  summary:
    "The main thrust and its evidence, as you'd explain it to someone else. Write it without looking back at the paper.",
  reconstruction:
    "Rebuild the method from memory: its assumptions, its steps, what's strong or weak, what it doesn't cite. Write it before rereading the method.",
  assumption: 'An assumption the paper makes here, and whether it holds.',
  future_work: 'An idea this paper leaves open.',
  figure: FIGURE_QUESTIONS,
}

export const EXIT_TEST_KINDS: readonly NoteKind[] = ['five_cs', 'summary', 'reconstruction']
export const isExitTest = (kind: NoteKind | null | undefined) => kind != null && EXIT_TEST_KINDS.includes(kind)

export const TEMPLATE: Partial<Record<NoteKind, string>> = {
  five_cs: (PASSES[0].fiveCs ?? []).map((line) => line.slice(0, line.indexOf(':') + 1)).join('\n'),
  figure: FIGURE_QUESTIONS,
}

/** An empty body, or one that is still exactly the old kind's template, takes the new kind's template; typed text stays. */
export function swapTemplate(body: string, from: NoteKind | null, to: NoteKind | null): string {
  const old = from === null ? undefined : TEMPLATE[from]
  if (body !== '' && body !== old) return body
  return (to === null ? undefined : TEMPLATE[to]) ?? ''
}

export const matchesKind = (note: Pick<Note, 'kind'>, filter: 'all' | 'plain' | NoteKind) =>
  filter === 'all' || (filter === 'plain' ? !note.kind : note.kind === filter)
