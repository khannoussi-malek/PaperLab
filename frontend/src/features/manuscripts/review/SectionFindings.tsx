import type { SectionRef, SectionReview } from '@/api/client'
import { Button } from '@/components/ui/button'
import { noteHref } from '@/lib/route'
import { failedReason, FINDING_ICON, LOST_REVIEW, FINDING_LABEL, findingTone, groupFindings, refChip, ROLE_LABEL } from './sectionReviewModel'

const AI = <span className="rounded bg-provenance-llm-surface px-1.5 py-px text-xs text-provenance-llm">AI</span>
const TONE_TEXT = { good: 'text-green-700 dark:text-green-500', warn: 'text-amber-700 dark:text-amber-500', bad: 'text-destructive', muted: 'text-muted-foreground' }
const CHIP = 'rounded-full border px-2 py-px text-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none'
const isLive = (r: SectionReview) => r.status === 'queued' || r.status === 'running'

type Props = {
  review: SectionReview
  /** Its section changed since: greyed, with Review again. */
  stale: boolean
  /** A review is queued or running: Review again would be refused. */
  busy?: boolean
  /** Polling failed: a live review can't be followed any more. */
  lost?: boolean
  hasWorkspace: boolean
  /** Selects the researcher's sentence in the editor. */
  onJump: (hash: string) => void
  onCancel: (id: string) => void
  onReviewAgain: (review: SectionReview) => void
}

// D118: a chip only moves the selection or opens the researcher's own note; nothing here copies or inserts.
function Chip({ chip, onJump }: { chip: SectionRef; onJump: Props['onJump'] }) {
  const text = refChip(chip)
  if (chip.kind === 'sentence' && chip.hash) {
    const hash = chip.hash
    return <button type="button" className={`${CHIP} hover:bg-muted`} title="Select this sentence" onClick={() => onJump(hash)}>{text}</button>
  }
  if (chip.kind === 'note' && chip.note_id && chip.paper_id) {
    const href = noteHref(chip.paper_id, chip.note_id)
    return (
      <button type="button" className={`${CHIP} hover:bg-muted`} title="Open the note in a new tab" onClick={() => window.open(href, '_blank', 'noopener')}>
        {text}<span className="sr-only"> (opens in a new tab)</span>
      </button>
    )
  }
  return <span className={`${CHIP} text-muted-foreground`}>{text}</span>
}

const Cancel = ({ review, onCancel }: Pick<Props, 'review' | 'onCancel'>) => (
  <Button size="xs" variant="ghost" onClick={() => onCancel(review.id)}>Cancel</Button>
)

/** One section review in the panel: what the reviewer found missing, unsupported and supported, by sentence and note. */
export function SectionFindings({ review, stale, busy = false, lost = false, hasWorkspace, onJump, onCancel, onReviewAgain }: Props) {
  const title = `“${review.title}”`
  if (stale) {
    return (
      <li className="flex items-center gap-2 rounded-md border bg-muted/40 px-2.5 py-1.5 text-sm text-muted-foreground">
        <span className="min-w-0 flex-1 truncate">{title}</span>
        {isLive(review) && <Cancel review={review} onCancel={onCancel} />}
        <Button size="xs" variant="outline" disabled={busy} onClick={() => onReviewAgain(review)}>Review again</Button>
      </li>
    )
  }
  const groups = groupFindings(review)
  return (
    <li>
      <article aria-label={`Section review of ${title}`} className="space-y-1.5 rounded-md border bg-card/60 px-2.5 py-2 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="font-medium">{title}</h4>
          {AI}
        </div>
        <p className="text-xs text-muted-foreground">
          Reviewed as: {ROLE_LABEL[review.role]}{review.role_source === 'chosen' && ' (you chose this)'}
        </p>
        <div>
          {isLive(review) && (lost
            ? <p className="flex items-center gap-2 text-xs text-muted-foreground">{LOST_REVIEW}<Button size="xs" variant="outline" disabled={busy} onClick={() => onReviewAgain(review)}>Review again</Button></p>
            : <p className="flex items-center gap-2 text-xs text-muted-foreground">Reviewing…<Cancel review={review} onCancel={onCancel} /></p>)}
          {review.status === 'failed' && <p className="text-xs text-muted-foreground">{failedReason(review.reason)}</p>}
          {review.status === 'interrupted' && <p className="text-xs text-muted-foreground">The review was interrupted. Run it again.</p>}
          {review.status === 'done' && groups.length === 0 && <p className="text-xs text-muted-foreground">Nothing to report for this section.</p>}
        </div>
        {groups.map(({ kind, findings }) => {
          const Icon = FINDING_ICON[kind]
          const label = FINDING_LABEL[kind]
          return (
            <div key={kind} role="group" aria-label={label} className="space-y-1">
              <h5 className={`flex items-center gap-1 text-xs font-semibold ${TONE_TEXT[findingTone(kind)]}`}><Icon aria-hidden className="size-3.5" />{label}</h5>
              <ul className="space-y-1">
                {findings.map((f, i) => (
                  <li key={i}>
                    <p>{f.point}</p>
                    {f.refs.length > 0 && <div className="mt-0.5 flex flex-wrap gap-1">{f.refs.map((r) => <Chip key={`${r.kind}${r.n}`} chip={r} onJump={onJump} />)}</div>}
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
        {review.dropped > 0 && (
          <p className="text-xs text-muted-foreground">{review.dropped === 1 ? "1 line wasn't in a usable form." : `${review.dropped} lines weren't in a usable form.`}</p>
        )}
        {!hasWorkspace && <p className="text-xs text-muted-foreground">Your notes weren't used — pick a workspace to include them.</p>}
      </article>
    </li>
  )
}
