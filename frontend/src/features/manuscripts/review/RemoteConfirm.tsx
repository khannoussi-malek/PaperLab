import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

type Props = { what: 'section' | 'text'; host: string; onSend: () => void; onCancel: () => void }

const remoteQuestion = (what: Props['what'], host: string) => `Your ${what} will be sent to ${host} and may cost money. Send it?`

/** The question and its two answers, for a dialog that already has a title. */
export function RemoteConfirm({ what, host, onSend, onCancel }: Props) {
  return (
    <>
      <p className="text-sm">{remoteQuestion(what, host)}</p>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <Button autoFocus onClick={onSend}>Send</Button>
      </DialogFooter>
    </>
  )
}

/** Asks before a start sends the researcher's text to a remote model; open while `host` is set. */
export function RemoteConfirmDialog({ what, host, onSend, onCancel }: Omit<Props, 'host'> & { host: string | null }) {
  return (
    <Dialog open={host !== null} onOpenChange={(open) => { if (!open) onCancel() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send to {host}?</DialogTitle>
          <DialogDescription className="sr-only">{host && remoteQuestion(what, host)}</DialogDescription>
        </DialogHeader>
        {host && <RemoteConfirm what={what} host={host} onSend={onSend} onCancel={onCancel} />}
      </DialogContent>
    </Dialog>
  )
}
