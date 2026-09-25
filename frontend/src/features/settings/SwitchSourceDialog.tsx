import { Download } from 'lucide-react'
import { useSwitchSearchSource } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { describePull } from './pullProgress'
import {
  NOT_PULLED,
  OLLAMA_MODEL,
  PULL_LABEL,
  switchBody,
  switchDialog,
  switchRefusal,
  type Library,
  type SourcePick,
  type Target,
} from './searchSources'
import { usePullModel } from './usePullModel'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  picks: SourcePick
  target: Target
  library: Library
}

/**
 * "Switch search to <label>?" (P2, D157): what goes where, and roughly what it costs for a cloud, before anything is
 * sent. Switch sends PUT /api/embedding/source, which probes the source first; a refusal stays in the dialog. Ollama
 * without nomic-embed-text offers M9's pull, never added to chat, then switches again by itself.
 */
export function SwitchSourceDialog({ open, onOpenChange, picks, target, library }: Props) {
  const switchSource = useSwitchSearchSource()
  const { state: pull, pull: startPull } = usePullModel(picks.connectionId ?? '', {
    addToChat: false,
    onDone: () => void send(),
  })
  const text = switchDialog(target, library)
  const refused = switchSource.error?.message
  const line = pull.status === 'pulling' ? pull.line : null
  const percent = line ? describePull({ status: line.status, total: line.total ?? null, completed: line.completed ?? null }).percent : null

  async function send() {
    try {
      await switchSource.mutateAsync(switchBody(picks))
      onOpenChange(false)
    } catch {
      // shown below from switchSource.error; the dialog stays open to pull, try again or cancel
    }
  }

  function openChange(next: boolean) {
    if (next) switchSource.reset() // a reopened dialog starts clean
    onOpenChange(next)
  }

  return (
    <Dialog open={open} onOpenChange={openChange}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-md')}>
        <DialogHeader>
          <DialogTitle>{text.title}</DialogTitle>
          <DialogDescription asChild>
            <div className="flex flex-col gap-2">
              {text.body.map((sentence) => (
                <p key={sentence}>{sentence}</p>
              ))}
            </div>
          </DialogDescription>
        </DialogHeader>
        {text.footnote.map((sentence) => (
          <p key={sentence} className="text-xs text-muted-foreground">
            {sentence}
          </p>
        ))}
        {refused && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{switchRefusal(refused, target.label)}</AlertDescription>
          </Alert>
        )}
        {refused === NOT_PULLED && pull.status !== 'pulling' && (
          <div>
            <Button variant="outline" onClick={() => void startPull(OLLAMA_MODEL)}>
              <Download aria-hidden />
              {PULL_LABEL}
            </Button>
          </div>
        )}
        {pull.status === 'pulling' && <Progress aria-label={`Pulling ${OLLAMA_MODEL}`} value={percent} />}
        {pull.status === 'error' && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{pull.message}</AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button disabled={switchSource.isPending || pull.status === 'pulling'} onClick={() => void send()}>
            Switch
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
