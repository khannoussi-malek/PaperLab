import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { RemoteConfirm } from './RemoteConfirm'
import { useStartReviewAll } from './useReview'

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

type Props = { open: boolean; onClose: () => void; manuscriptId: string }

/** Review → Review all files: the estimate first, a confirm above 30 checks, then (for a remote model) whether to send. */
export function ReviewAllDialog({ open, onClose, manuscriptId }: Props) {
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Review all files</DialogTitle>
          <DialogDescription>PaperLab checks every citation in every .tex file and gives one list. It never rewrites your text.</DialogDescription>
        </DialogHeader>
        <Body manuscriptId={manuscriptId} onClose={onClose} />
      </DialogContent>
    </Dialog>
  )
}

/** Mounted only while the dialog is open, so the estimate is counted again on every open. */
function Body({ manuscriptId, onClose }: { manuscriptId: string; onClose: () => void }) {
  const estimate = useQuery({
    queryKey: ['reviewEstimate', manuscriptId],
    queryFn: () => api.reviewEstimate(manuscriptId),
    staleTime: 0,
    refetchOnWindowFocus: false, // every GET splits every file: count once per open
  })
  const { startAll, startAllError, confirmHost } = useStartReviewAll(manuscriptId)
  const [busy, setBusy] = useState(false)
  const est = estimate.data

  if (estimate.isError) {
    return (
      <>
        <p role="alert" className="text-sm text-destructive">Couldn't count the checks. Close and try again.</p>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button></DialogFooter>
      </>
    )
  }
  if (!est) {
    return (
      <>
        <p aria-live="polite" className="text-sm text-muted-foreground">Counting the checks…</p>
        <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button></DialogFooter>
      </>
    )
  }

  const go = async (confirmRemote: boolean) => {
    setBusy(true)
    try {
      await startAll(confirmRemote, est.needs_confirm)
      onClose()
    } catch {
      // the refusal is shown from the mutation's state (startAllError or confirmHost)
    } finally {
      setBusy(false)
    }
  }

  if (confirmHost) return <RemoteConfirm what="text" host={confirmHost} onSend={() => void go(true)} onCancel={onClose} />

  const n = est.pairs
  return (
    <>
      <div className="space-y-2">
        <p className="text-sm font-medium">{plural(n, 'check', 'checks')} across {plural(est.files.length, 'file', 'files')}</p>
        <ul className="space-y-0.5 text-sm text-muted-foreground">
          {est.files.map((f) => <li key={f.path}>{f.path}: {plural(f.pairs, 'check', 'checks')}</li>)}
        </ul>
        {est.needs_confirm && (
          <p className="text-sm">More than {est.confirm_above} checks. This can take a long time on a local model.</p>
        )}
        {n === 0 && <p className="text-sm text-muted-foreground">There is nothing to check yet.</p>}
      </div>
      {startAllError && <p role="alert" className="text-sm text-destructive">{startAllError}</p>}
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button disabled={busy || n === 0} onClick={() => void go(false)}>
          {busy ? 'Starting…' : `Run ${plural(n, 'check', 'checks')}`}
        </Button>
      </DialogFooter>
    </>
  )
}
