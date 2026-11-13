import { useState } from 'react'
import { isConflict, type DraftReview, type DraftReviewEstimate } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DraftReviewResult } from './DraftReviewResult'
import { RemoteConfirm } from './RemoteConfirm'
import { fullConfirmText, isLive, modeText, reasonText, startBody, startError, type DraftEstimate, type DraftMode, type DraftStart } from './draftReviewModel'
import { remoteHost } from './reviewModel'
import { useDraftReview } from './useDraftReview'

const AI = <span className="inline-block rounded bg-provenance-llm-surface px-1.5 py-px text-xs text-provenance-llm">AI review</span>

type Props = { manuscriptId: string; open: boolean; onClose: () => void }

/** Review → Tough draft review: both estimates first (Light by default), then progress, then the issues. */
export function DraftReviewDialog({ manuscriptId, open, onClose }: Props) {
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Tough draft review</DialogTitle>
          <DialogDescription>PaperLab's reviewers read the whole draft and list its biggest problems. Each point quotes your own text and says when it is done. It never rewrites your text.</DialogDescription>
        </DialogHeader>
        <Body manuscriptId={manuscriptId} onClose={onClose} />
      </DialogContent>
    </Dialog>
  )
}

function Body({ manuscriptId, onClose }: Omit<Props, 'open'>) {
  const { review, estimate, estimateFailed, start, cancel } = useDraftReview(manuscriptId)
  const [mode, setMode] = useState<DraftMode>('light')
  const [confirming, setConfirming] = useState(false)
  const [remote, setRemote] = useState<{ host: string; body: DraftStart } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const live = isLive(review)

  const send = async (body: DraftStart) => {
    setBusy(true); setError(null); setRemote(null)
    try {
      await start(body)
      setConfirming(false)
    } catch (e) {
      const host = remoteHost(e)
      if (host) setRemote({ host, body })
      else if (isConflict(e, 'full_needs_confirm')) setConfirming(true)
      else setError(startError(e))
    } finally {
      setBusy(false)
    }
  }
  const stop = async (reviewId: string) => {
    try { await cancel(reviewId) } catch { setError("The review couldn't be cancelled. Try again.") }
  }

  return (
    <div className="space-y-4">
      <div>{AI}</div>
      {live && review && <Progress review={review} onCancel={() => void stop(review.id)} />}
      {!live && review && <DraftReviewResult review={review} />}
      {!live && remote && (
        <RemoteConfirm what="text" host={remote.host} onSend={() => void send({ ...remote.body, confirm_remote: true })} onCancel={() => setRemote(null)} />
      )}
      {!live && !remote && confirming && estimate && (
        <FullConfirm text={fullConfirmText(estimate.modes.find((m) => m.mode === 'full') ?? estimate.modes[0])} busy={busy} onRun={() => void send(startBody('full', false, true))} onCancel={() => setConfirming(false)} />
      )}
      {!live && !remote && !confirming && (
        <StartControls
          estimate={estimate}
          estimateFailed={estimateFailed}
          mode={mode}
          again={review !== null}
          busy={busy}
          onMode={setMode}
          onStart={() => (mode === 'full' ? setConfirming(true) : void send(startBody(mode, false, false)))}
          onClose={onClose}
        />
      )}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

function Progress({ review, onCancel }: { review: DraftReview; onCancel: () => void }) {
  return (
    <div className="space-y-2 text-sm" aria-live="polite">
      <p>{review.stage ?? 'Starting…'}</p>
      <p className="text-xs text-muted-foreground">{`${review.calls_done} of ${review.calls_max} calls`}</p>
      <Button size="sm" variant="outline" onClick={onCancel}>Cancel</Button>
    </div>
  )
}

function FullConfirm({ text, busy, onRun, onCancel }: { text: string; busy: boolean; onRun: () => void; onCancel: () => void }) {
  return (
    <>
      <p className="text-sm">{text}</p>
      <DialogFooter>
        <Button variant="outline" autoFocus onClick={onCancel}>Cancel</Button>{/* focus on Cancel: Enter must not spend time */}
        <Button disabled={busy} onClick={onRun}>Run</Button>
      </DialogFooter>
    </>
  )
}

function StartControls({ estimate, estimateFailed, mode, again, busy, onMode, onStart, onClose }: {
  estimate: DraftReviewEstimate | null
  estimateFailed: boolean
  mode: DraftMode
  again: boolean
  busy: boolean
  onMode: (mode: DraftMode) => void
  onStart: () => void
  onClose: () => void
}) {
  if (estimateFailed) return <p className="text-sm">The estimate could not be loaded. Close and try again.</p>
  if (!estimate) return <p className="text-sm text-muted-foreground">Loading the estimates…</p>
  const label = mode === 'full' ? 'Start full review' : again ? 'Start again' : 'Start review'
  return (
    <>
      {estimate.parts > 1 && !estimate.too_long && (
        <div className="space-y-1 text-sm">
          <p>{`Long draft: reviewed in ${estimate.parts} parts, one section group at a time.`}</p>
          <p className="text-muted-foreground">A draft this long gets the light review only.</p>
        </div>
      )}
      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium">How deep to review</legend>
        {estimate.modes.map((m: DraftEstimate) => (
          <label key={m.mode} className="flex cursor-pointer items-start gap-2 text-sm">
            <input type="radio" name="draft-review-mode" value={m.mode} checked={mode === m.mode} onChange={() => onMode(m.mode)} className="mt-1" />
            <span>{modeText(m)}</span>
          </label>
        ))}
      </fieldset>
      {estimate.too_long && <p className="text-sm text-destructive">{reasonText('paper_too_long')}</p>}
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button disabled={busy || estimate.too_long} onClick={onStart}>{label}</Button>
      </DialogFooter>
    </>
  )
}
