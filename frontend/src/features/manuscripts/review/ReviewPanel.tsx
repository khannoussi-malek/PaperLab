import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { CheckItem, SectionReview } from '@/api/client'
import { Button } from '@/components/ui/button'
import { chunkHref } from '@/lib/route'
import { RemoteConfirmDialog } from './RemoteConfirm'
import { SectionFindings } from './SectionFindings'
import { statusLine } from './sectionReviewModel'
import { couldntCheck, isLive, isPending, itemTone, reasonCopy, VERDICT_LABEL, type Tone } from './reviewModel'
import { useCiteProposals, type useReview } from './useReview'

type Review = Pick<ReturnType<typeof useReview>, 'run' | 'items' | 'dismissed' | 'startError' | 'cancel' | 'dismiss' | 'restore'>
type Props = {
  manuscriptId: string
  review: Review
  /** Items whose sentence changed or vanished since the check. */
  stale: CheckItem[]
  onJump: (hash: string) => void
  /** Pins the paper and inserts its citation; resolves to a problem to show, or null. */
  onCite: (hash: string, paperId: string) => Promise<string | null>
  onCheckAgain: () => void
  /** The open file's section reviews, shown above the citations. */
  sections?: {
    reviews: SectionReview[]
    /** Reviews whose section changed since. */
    stale: SectionReview[]
    hasWorkspace: boolean
    /** A section review is queued or running. */
    live?: boolean
    /** Polling the section reviews failed. */
    lost?: boolean
    onCancel: (id: string) => void
    onReviewAgain: (review: SectionReview) => void
  }
}

const OPEN_KEY = 'paperlab-review-panel-open'
const readOpen = () => { try { return localStorage.getItem(OPEN_KEY) !== 'false' } catch { return true } }
const writeOpen = (open: boolean) => { try { localStorage.setItem(OPEN_KEY, String(open)) } catch { /* private window: it just won't be remembered */ } }

const TONE: Record<Tone, string> = {
  good: 'border-l-green-600', warn: 'border-l-amber-600', bad: 'border-l-destructive', muted: 'border-l-muted-foreground',
}
const AI = <span className="rounded bg-provenance-llm-surface px-1.5 py-px text-xs text-provenance-llm">AI</span>
const RUN_NOTE: Record<string, string> = {
  cancelled: 'The check was cancelled. Run it again whenever you like.',
  interrupted: 'The check was interrupted. Run it again.',
  failed: "The check couldn't finish. Try again.",
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
      <ul className="space-y-1.5">{children}</ul>
    </div>
  )
}

function CitedRow({ item, onJump }: { item: CheckItem; onJump: Props['onJump'] }) {
  const failed = couldntCheck(item)
  const pending = isPending(item)
  const reason = item.reason && !failed ? item.reason : null
  const open = () => window.open(chunkHref(item.paper_id!, item.chunk_id!, item.page ?? 1), '_blank', 'noopener')
  return (
    <li className={`rounded-md border border-l-4 bg-card/60 px-2.5 py-1.5 text-sm ${TONE[itemTone(item)]}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium">{pending ? 'Checking…' : VERDICT_LABEL[item.verdict ?? ''] ?? 'Not checked'}</span>
        {item.verdict && !pending && AI}
        {item.cite_key && <code>{item.cite_key}</code>}
      </div>
      <button type="button" className="mt-0.5 block w-full rounded text-left hover:underline focus-visible:ring-2 focus-visible:ring-ring" onClick={() => onJump(item.sentence_hash)}>{item.sentence}</button>
      {failed && <p className="text-xs text-muted-foreground">{reasonCopy(item.reason)}</p>}
      {reason && <p className="text-xs text-muted-foreground">{reason}</p>}
      {item.quote && item.paper_id && item.chunk_id && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          “{item.quote}”{' '}
          <a href={chunkHref(item.paper_id, item.chunk_id, item.page ?? 1)} className="underline" onClick={(e) => { e.preventDefault(); open() }}>Page {item.page ?? 1}</a>
        </p>
      )}
    </li>
  )
}

function ClaimRow({ item, manuscriptId, dismissed, review, onJump, onCite }: { item: CheckItem; manuscriptId: string; dismissed: boolean; review: Review; onJump: Props['onJump']; onCite: Props['onCite'] }) {
  const found = useCiteProposals(manuscriptId, item.sentence)
  const [problem, setProblem] = useState<string | null>(null)
  const cite = async (paperId: string) => setProblem(await onCite(item.sentence_hash, paperId))
  if (isPending(item)) {
    return (
      <li className={`rounded-md border border-l-4 bg-card/60 px-2.5 py-1.5 text-sm ${TONE.muted}`}>
        <span className="text-xs font-medium">Checking…</span>
        <button type="button" className="mt-0.5 block w-full rounded text-left hover:underline focus-visible:ring-2 focus-visible:ring-ring" onClick={() => onJump(item.sentence_hash)}>{item.sentence}</button>
      </li>
    )
  }
  if (couldntCheck(item)) {
    return (
      <li className={`rounded-md border border-l-4 bg-card/60 px-2.5 py-1.5 text-sm ${TONE.muted}`}>
        <span className="text-xs font-medium">Couldn't check</span>
        <button type="button" className="mt-0.5 block w-full rounded text-left hover:underline focus-visible:ring-2 focus-visible:ring-ring" onClick={() => onJump(item.sentence_hash)}>{item.sentence}</button>
        <p className="text-xs text-muted-foreground">{reasonCopy(item.reason)}</p>
      </li>
    )
  }
  if (dismissed) {
    return (
      <li className="flex items-center gap-2 rounded-md px-2.5 py-1 text-xs text-muted-foreground">
        <span className="min-w-0 flex-1 truncate">Dismissed · {item.sentence}</span>
        <Button size="xs" variant="ghost" onClick={() => void review.restore(item.sentence_hash)}>Restore</Button>
      </li>
    )
  }
  return (
    <li className={`rounded-md border border-l-4 bg-card/60 px-2.5 py-1.5 text-sm ${TONE.warn}`}>
      <div className="flex items-center gap-2 text-xs"><span className="font-medium">Needs a citation</span>{AI}</div>
      <button type="button" className="mt-0.5 block w-full rounded text-left hover:underline focus-visible:ring-2 focus-visible:ring-ring" onClick={() => onJump(item.sentence_hash)}>{item.sentence}</button>
      <div className="mt-1 flex gap-2">
        <Button size="xs" variant="outline" disabled={found.pending} onClick={found.ask}>{found.pending ? 'Finding…' : 'Find papers'}</Button>
        <Button size="xs" variant="ghost" onClick={() => void review.dismiss(item.sentence_hash)}>Not a claim</Button>
      </div>
      <RemoteConfirmDialog what="text" host={found.confirmHost} onSend={found.confirm} onCancel={found.dismissConfirm} />
      {(found.message || problem) && <p role="status" className="mt-1 text-xs text-muted-foreground">{problem ?? found.message}</p>}
      {found.proposals.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {found.proposals.map((p) => (
            <li key={p.paperId} className="flex items-start gap-2 text-xs">
              <div className="min-w-0 flex-1">
                <code>{p.key}</code> <span className="text-muted-foreground">· p. {p.page ?? 1}</span>
                <p className="text-muted-foreground">“{p.quote}”</p>
              </div>
              <Button size="xs" onClick={() => void cite(p.paperId)}>Cite this</Button>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

function SectionReviews({ reviews, stale, hasWorkspace, live: busy = false, lost, onCancel, onReviewAgain, onJump }: NonNullable<Props['sections']> & Pick<Props, 'onJump'>) {
  const staleIds = new Set(stale.map((r) => r.id))
  const live = reviews.filter((r) => !staleIds.has(r.id))
  const card = (r: SectionReview, isStale: boolean) => (
    <SectionFindings key={r.id} review={r} stale={isStale} busy={busy} lost={lost} hasWorkspace={hasWorkspace} onJump={onJump} onCancel={onCancel} onReviewAgain={onReviewAgain} />
  )
  return (
    <>
      {live.length > 0 && <Group title="Section review">{live.map((r) => card(r, false))}</Group>}
      {stale.length > 0 && <Group title="Changed since reviewed">{stale.map((r) => card(r, true))}</Group>}
    </>
  )
}

/** Results under the editor: the citations checked, claims with no citation, and what changed since. */
export function ReviewPanel({ manuscriptId, review, stale, onJump, onCite, onCheckAgain, sections }: Props) {
  const [open, setOpen] = useState(readOpen)
  const { run, items, dismissed, startError } = review
  const sectionReviews = sections?.reviews ?? []
  // Always mounted, so a review's start and finish are announced (a region created with its text is not).
  const announcer = sections && (
    <div role="status" aria-live="polite" aria-label="Section review status" className="sr-only">
      {sectionReviews.map((r) => <p key={r.id}>{statusLine(r, sections.lost)}</p>)}
    </div>
  )
  if (!run && items.length === 0 && !startError && sectionReviews.length === 0) return announcer ?? null
  const title = sectionReviews.length > 0 ? 'Review' : 'Citation check'
  const toggle = () => { writeOpen(!open); setOpen(!open) }
  const staleIds = new Set(stale.map((i) => i.id))
  const live = items.filter((i) => !staleIds.has(i.id))
  const cited = live.filter((i) => i.kind === 'cited')
  const claims = live.filter((i) => i.kind === 'uncited' && i.verdict !== 'not_claim')
  const finished = run && !isLive(run)
  const empty = finished && run.status === 'done' && items.length === 0
  return (
    <>
    {announcer}
    <section aria-label={title} className="max-h-[40%] shrink-0 overflow-auto border-t border-glass-border">
      <button type="button" aria-expanded={open} className="flex w-full items-center gap-1.5 px-3 py-1.5 text-left text-sm font-medium focus-visible:ring-2 focus-visible:ring-ring" onClick={toggle}>
        {open ? <ChevronDown aria-hidden className="size-4" /> : <ChevronRight aria-hidden className="size-4" />}
        {title}
      </button>
      {open && (
        <div className="space-y-3 px-3 pb-3">
          {sections && <SectionReviews {...sections} onJump={onJump} />}
          {run && isLive(run) && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
              Checking {run.done} of {run.total}…
              <Button size="xs" variant="ghost" onClick={() => void review.cancel()}>Cancel</Button>
            </p>
          )}
          {startError && <p role="alert" className="text-xs text-destructive">{startError}</p>}
          {finished && run.status !== 'done' && (
            <p role="status" className="text-xs text-muted-foreground">
              {run.status === 'failed' && run.reason === 'no_model' ? 'Add a model in Settings to run the reviewer.' : RUN_NOTE[run.status]}
            </p>
          )}
          {empty && <p className="text-sm text-muted-foreground">Nothing to check — no sentences cite a paper.</p>}
          {run && run.uncited_skipped > 0 && (
            <p className="text-xs text-muted-foreground">
              {run.uncited_skipped === 1 ? "1 more sentence wasn't checked. Select it to check." : `${run.uncited_skipped} more sentences weren't checked. Select them to check.`}
            </p>
          )}
          {cited.length > 0 && <Group title="Citations">{cited.map((i) => <CitedRow key={i.id} item={i} onJump={onJump} />)}</Group>}
          {claims.length > 0 && (
            <Group title="Claims with no citation">
              {claims.map((i) => <ClaimRow key={i.id} item={i} manuscriptId={manuscriptId} dismissed={dismissed.includes(i.sentence_hash)} review={review} onJump={onJump} onCite={onCite} />)}
            </Group>
          )}
          {stale.length > 0 && (
            <Group title="Changed since checked">
              {stale.map((i) => (
                <li key={i.id} className="flex items-center gap-2 rounded-md border bg-muted/40 px-2.5 py-1.5 text-sm text-muted-foreground">
                  <span className="min-w-0 flex-1 truncate" title={i.sentence}>{i.sentence}</span>
                  <Button size="xs" variant="outline" onClick={onCheckAgain}>Check again</Button>
                </li>
              ))}
            </Group>
          )}
        </div>
      )}
    </section>
    </>
  )
}
