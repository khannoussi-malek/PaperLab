import { useState } from 'react'
import type { Role, SectionSpan } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { RemoteConfirm } from './RemoteConfirm'
import { remoteHost } from './reviewModel'
import { REVIEWABLE_ROLES, ROLE_LABEL } from './sectionReviewModel'
import { sectionStartError } from './useSectionReview'

const SELECT_CLASS =
  'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-xs focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none'
const NO_SECTION = 'Put the cursor inside a section first.'

type Props = {
  /** The section under the cursor (null: none); open while set. */
  target: { section: Pick<SectionSpan, 'title' | 'guess'> | null; role?: Role | null } | null
  onClose: () => void
  /** Saves what is pending, then starts; `role` is null when the guess stands. Rejects with the server's refusal. */
  onStart: (role: Role | null, confirmRemote: boolean) => Promise<unknown>
}

/** Review → Review this section: confirm what kind of section it is, then (for a remote model) whether to send it. */
export function SectionReviewDialog({ target, onClose, onStart }: Props) {
  return (
    <Dialog open={target !== null} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Review this section</DialogTitle>
          <DialogDescription>PaperLab's reviewer says what the section is missing and which claims lack support. It never rewrites your text.</DialogDescription>
        </DialogHeader>
        {target && <Body key={target.section?.title ?? ''} target={target} onClose={onClose} onStart={onStart} />}
      </DialogContent>
    </Dialog>
  )
}

function Body({ target, onClose, onStart }: Props & { target: NonNullable<Props['target']> }) {
  const { section } = target
  const guess = section?.guess && REVIEWABLE_ROLES.includes(section.guess) ? section.guess : null
  const [role, setRole] = useState<Role | ''>(target.role ?? guess ?? '')
  const [host, setHost] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!section) {
    return (
      <>
        <p>{NO_SECTION}</p>
        <DialogFooter><Button variant="outline" onClick={onClose}>Close</Button></DialogFooter>
      </>
    )
  }
  const send = async (confirmRemote: boolean) => {
    if (!role) return
    setBusy(true); setError(null); setHost(null)
    try {
      await onStart(role === guess ? null : role, confirmRemote)
      onClose()
    } catch (e) {
      const remote = remoteHost(e)
      if (remote) setHost(remote)
      else setError(sectionStartError(e))
    } finally {
      setBusy(false)
    }
  }
  if (host) return <RemoteConfirm what="section" host={host} onSend={() => void send(true)} onCancel={onClose} />
  return (
    <>
      <div className="space-y-1.5">
        <label htmlFor="section-review-role" className="text-sm font-medium">Review “{section.title}” as:</label>
        <select id="section-review-role" className={SELECT_CLASS} value={role} aria-describedby={guess ? undefined : 'section-review-why'} onChange={(e) => setRole(e.target.value as Role | '')}>
          <option value="" disabled>Choose a kind of section</option>
          {REVIEWABLE_ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
        </select>
        {!guess && <p id="section-review-why" className="text-xs text-muted-foreground">PaperLab couldn't tell what kind of section this is — choose one.</p>}
      </div>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button disabled={!role || busy} onClick={() => void send(false)}>{busy ? 'Starting…' : 'Review'}</Button>
      </DialogFooter>
    </>
  )
}
