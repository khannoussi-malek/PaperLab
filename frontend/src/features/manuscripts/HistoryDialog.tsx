import { useState } from 'react'
import { useManuscriptSnapshots, useRestoreSnapshot } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { manuscriptFailure } from './errors'

type Props = { manuscriptId: string; open: boolean; onOpenChange: (open: boolean) => void; onRestored: () => void
  /** Saves what is pending; false means it could not (a conflict), so nothing is restored. */
  beforeRestore: () => Promise<boolean>
}

const REASON: Record<string, string> = {
  compile: 'Compiled', autosave: 'Autosaved',
  before_restore: 'Before a restore',
  before_mcp: 'Before a Claude edit (MCP)',
}
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/** Earlier versions of the whole manuscript. Restoring asks here, in the dialog, before it replaces anything. */
export function HistoryDialog({ manuscriptId, open, onOpenChange, onRestored, beforeRestore }: Props) {
  const snapshots = useManuscriptSnapshots(manuscriptId)
  const restore = useRestoreSnapshot()
  const [confirming, setConfirming] = useState<string | null>(null)

  const doRestore = async (snapshotId: string) => {
    if (!(await beforeRestore())) {
      setConfirming(null)
      onOpenChange(false) // the editor shows why the save stopped
      return
    }
    restore.mutate({ id: manuscriptId, snapshotId }, { onSuccess: () => { setConfirming(null); onRestored() } })
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { setConfirming(null); onOpenChange(next) }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>History</DialogTitle>
          <DialogDescription>Earlier versions of this manuscript, newest first.</DialogDescription>
        </DialogHeader>
        {restore.error && <Alert variant="destructive"><AlertDescription>{manuscriptFailure(restore.error)}</AlertDescription></Alert>}
        {snapshots.error && <Alert variant="destructive"><AlertDescription>{snapshots.error.message}</AlertDescription></Alert>}
        {snapshots.data?.length === 0 && <p className="text-sm text-muted-foreground">No earlier versions yet. One is kept each time you compile.</p>}
        <ul className="flex max-h-80 flex-col gap-1 overflow-auto">
          {snapshots.data?.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-2 rounded-md border border-glass-border px-3 py-2 text-sm">
              <span>{when(s.created_at)} <span className="text-muted-foreground">{REASON[s.reason] ?? s.reason}</span></span>
              {confirming === s.id ? (
                <span className="flex items-center gap-2">
                  <span>Replace the current files with this version?</span>
                  <Button size="sm" variant="destructive" disabled={restore.isPending} onClick={() => void doRestore(s.id)}>Restore</Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>Cancel</Button>
                </span>
              ) : (
                <Button size="sm" variant="outline" onClick={() => setConfirming(s.id)}>Restore…</Button>
              )}
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  )
}
