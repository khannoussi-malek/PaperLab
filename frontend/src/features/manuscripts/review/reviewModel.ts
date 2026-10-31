import { isConflict, type ApiError, type CheckItem, type ReviewSentence } from '@/api/client'

export const VERDICT_LABEL: Record<string, string> = {
  supported: 'Supports',
  partially_supported: 'Partly supports',
  not_supported: "Doesn't support",
  not_addressed: "Doesn't address",
  cannot_verify: "Can't tell",
  claim: 'Needs a citation',
  not_claim: 'Not a claim',
}

export type Tone = 'good' | 'warn' | 'bad' | 'muted'

export function itemTone(item: Pick<CheckItem, 'verdict'>): Tone {
  switch (item.verdict) {
    case 'supported': return 'good'
    case 'partially_supported':
    case 'claim': return 'warn'
    case 'not_supported': return 'bad'
    default: return 'muted'
  }
}

export type Mark = { from: number; to: number; items: CheckItem[] }

/** Joins results to the sentences the editor holds now, by hash; items whose sentence changed or vanished are stale. */
export function marksFor(items: CheckItem[], spans: ReviewSentence[], dismissed: readonly string[] = []): { marks: Mark[]; stale: CheckItem[] } {
  const byHash = new Map(spans.map((s) => [s.hash, s]))
  const gone = new Set(dismissed)
  const grouped = new Map<string, Mark>()
  const stale: CheckItem[] = []
  for (const item of items) {
    // Settled claims need no re-check when their sentence changes, so they are never "stale".
    if (item.kind === 'uncited' && (item.verdict === 'not_claim' || gone.has(item.sentence_hash))) continue
    const span = byHash.get(item.sentence_hash)
    if (!span) { stale.push(item); continue }
    const mark = grouped.get(span.hash)
    if (mark) grouped.set(span.hash, { ...mark, items: [...mark.items, item] })
    else grouped.set(span.hash, { from: span.start, to: span.end, items: [item] })
  }
  return { marks: [...grouped.values()].sort((a, b) => a.from - b.from), stale }
}

const SAFE_KEY = /^[\w:.+-]+$/
const END = /[.?!]/
const CLOSERS = /[)"}]/

/** Where `\citep{key}` goes: before the sentence's final . ? or ! (closers after it stay after). */
export function citeThisEdit(doc: string, span: { start: number; end: number }, key: string): { from: number; insert: string } {
  if (!SAFE_KEY.test(key)) throw new Error(`Unsafe citation key: ${JSON.stringify(key)}`)
  let at = span.end
  while (at > span.start && CLOSERS.test(doc[at - 1])) at--
  if (!(at > span.start && END.test(doc[at - 1]))) at = span.end // no terminal mark: cite at the very end
  else at--
  const prev = doc[at - 1]
  const lead = at === 0 || /[\s~]/.test(prev) ? '' : ' '
  return { from: at, insert: `${lead}\\citep{${key}}` }
}

const REASON_COPY: Record<string, string> = {
  key_not_found: 'This key matches no paper in the library',
  paper_not_in_library: 'This paper is not in the library',
  no_text: 'This paper has no text yet',
  not_ready: 'This paper is still being read. Try again soon.',
  claim_too_long: 'This sentence is too long to check',
  empty_claim: 'There was nothing to check in this sentence',
  claim_scope: "This sentence couldn't be matched to a paper",
  no_model: 'No model is set up. Add one in Settings.',
  cancelled: 'Stopped before this one was checked.',
  model_error: "The model didn't give a usable answer",
  check_failed: "The model didn't give a usable answer",
  remote_model_needs_confirm: 'The default model is now a cloud model. Check again to confirm sending your text.',
}
/** A failed or unverifiable row's reason in plain words; an unknown code is not blamed on the model. */
export const reasonCopy = (reason: string | null): string => (reason && REASON_COPY[reason]) || "This one couldn't be checked."
export const REASON_CODES = Object.keys(REASON_COPY)

/** Not judged yet: waiting for its turn or being checked now. */
export const isPending = (item: Pick<CheckItem, 'status'>) => item.status === 'queued' || item.status === 'running'

/** A settled row the reviewer could not judge (as opposed to a finding). */
export const couldntCheck = (item: Pick<CheckItem, 'status' | 'verdict'>) =>
  item.status === 'failed' || item.status === 'interrupted' || (item.status === 'done' && (item.verdict === 'cannot_verify' || !item.verdict))

export const isLive = (run: { status: string } | null) => run?.status === 'queued' || run?.status === 'running'

/** Where the text would go when the start refused for a remote model (409 remote_model_needs_confirm), else null. */
export function remoteHost(e: unknown): string | null {
  return isConflict(e, 'remote_model_needs_confirm') ? String((e as ApiError).body.host ?? 'a remote model') : null
}
