import type { Check, Note, NoteKind } from '@/api/client'
import { refusal, type ChatProblem } from '@/features/chat/refusals'

type ExitKind = Extract<NoteKind, 'five_cs' | 'summary' | 'reconstruction'>
export type CheckLine = Check['lines'][number]
export type ExitTestStatus = 'not_written' | 'not_checked' | 'stale' | { missing: number; unsupported: number; at: string }

const LABEL: Record<ExitKind, string> = { five_cs: 'five Cs', summary: 'summary', reconstruction: 'reconstruction' }

export const isExitTest = (kind: NoteKind | null): kind is ExitKind => kind !== null && kind in LABEL
export const exitTestLabel = (kind: ExitKind) => LABEL[kind]

/** The newest note of `kind` the reader wrote. An AI note of that kind doesn't count (D118). */
export const exitTestNote = (notes: Note[], kind: NoteKind): Note | undefined =>
  notes
    .filter((note) => note.kind === kind && note.provenance === 'human')
    .reduce<Note | undefined>((newest, note) => (!newest || note.created_at > newest.created_at ? note : newest), undefined)

export function exitTestStatus(note: Note | undefined, check: Check | undefined): ExitTestStatus {
  if (!note) return 'not_written'
  if (!check) return 'not_checked'
  if (check.stale) return 'stale'
  const count = (verdict: CheckLine['verdict']) => check.lines.filter((line) => line.verdict === verdict).length
  return { missing: count('missing'), unsupported: count('unsupported'), at: check.created_at }
}

/** The Reading control's row for one exit test, and what its button does. */
export function exitTestLine(kind: ExitKind, status: ExitTestStatus): { text: string; action: 'write' | 'open' } {
  const label = `Your ${LABEL[kind]}`
  if (status === 'not_written') return { text: `${label}: not written yet`, action: 'write' }
  if (status === 'not_checked') return { text: `${label}: not checked yet`, action: 'open' }
  if (status === 'stale') return { text: `${label}: changed since its check`, action: 'open' }
  const date = new Date(status.at).toLocaleDateString(undefined, { dateStyle: 'medium' })
  return { text: `${label}: checked ${date}: ${status.missing} missing, ${status.unsupported} unsupported`, action: 'open' }
}

const STREAMED = /^(Missing|Unsupported|Supported): (\S.*)$/

/** A stream token is one line the server kept, "Missing: …". Anything else is dropped; nothing else is parsed here. */
export function streamedLine(token: string): CheckLine | null {
  const match = STREAMED.exec(token.trim())
  return match ? { verdict: match[1].toLowerCase() as CheckLine['verdict'], text: match[2] } : null
}

const plain = (message: string, extra: Partial<ChatProblem> = {}): ChatProblem => ({ message, retryable: false, reindex: false, ...extra })
const PROBLEMS: Record<string, ChatProblem> = {
  not_your_text: plain('Only text you wrote can be checked. This note came from AI.'),
  not_checkable: plain('Only a Five Cs, Summary or Reconstruction note can be checked.'),
  nothing_written: plain('Write your answers first: this note has only its headings.'),
  note_too_long: plain('A check reads up to 8,000 characters. Shorten the note first.'),
  note_not_on_one_paper: plain('A check reads one paper. Link this note to exactly one paper.'),
  needs_full_text: plain("A check reads the paper's sections. Attach its PDF first."),
  no_model: plain('Add a model in Settings to check your notes.', { settings: true }),
}

/** A check refused before streaming, in words; the codes chat already knows go through its `refusal`. */
export function checkProblem(status: number, detail: string, kind: NoteKind): ChatProblem {
  if (detail === 'lens_empty')
    return plain(
      kind === 'reconstruction'
        ? "This paper has no sections for How they did it, so a reconstruction can't be checked. Fix a section's role in the Lens tab."
        : 'This paper has no sections to check against.',
    )
  return PROBLEMS[detail] ?? refusal(status, detail)
}
