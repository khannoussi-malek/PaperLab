import { Lock, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useEmbeddingStatus, useReindexLibrary } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { indexedLine, staleChunks } from './embeddingStatus'

/** The "Embedding model" section: the model in use (locked once anything is indexed), and a confirmed re-index. */
export function EmbeddingSettings() {
  const status = useEmbeddingStatus()
  const reindex = useReindexLibrary()
  const [confirmOpen, setConfirmOpen] = useState(false)

  async function confirmReindex() {
    await reindex.mutateAsync()
    setConfirmOpen(false)
  }

  return (
    <section aria-labelledby="embedding-model-heading" className="flex flex-col gap-4">
      <h2 id="embedding-model-heading" className="font-heading text-xl font-semibold">
        Embedding model
      </h2>

      {status.data === undefined ? (
        status.isError ? (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{status.error.message}</AlertDescription>
            <AlertAction>
              <Button variant="outline" size="xs" onClick={() => void status.refetch()}>
                Retry
              </Button>
            </AlertAction>
          </Alert>
        ) : (
          <p className="text-muted-foreground">Loading…</p>
        )
      ) : (
        <div className="flex flex-col gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="embedding-model" className="flex items-center gap-1.5 text-sm font-medium">
              {status.data.chunks > 0 && <Lock aria-hidden className="size-3.5" />}
              Embedding model
            </Label>
            <Select value={status.data.model} disabled={status.data.chunks > 0}>
              <SelectTrigger id="embedding-model" aria-label="Embedding model" disabled={status.data.chunks > 0} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={status.data.model}>{status.data.model}</SelectItem>
              </SelectContent>
            </Select>
            {indexedLine(status.data) && (
              <p className="embedding-indexed text-xs tabular-nums text-muted-foreground">{indexedLine(status.data)}</p>
            )}
          </div>

          {staleChunks(status.data) > 0 && (
            <Alert variant="destructive" className="border-glass-border">
              <AlertDescription>
                {staleChunks(status.data)} chunks were indexed with another model. Chat on those papers is refused until you re-index.
              </AlertDescription>
            </Alert>
          )}

          <div>
            <Button variant="outline" onClick={() => setConfirmOpen(true)}>
              <RefreshCw aria-hidden />
              Re-index library
            </Button>
          </div>

          {reindex.data && (
            <p role="status" className="text-sm text-muted-foreground">
              Re-indexing {reindex.data.papers} papers in the background.
            </p>
          )}
        </div>
      )}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-md')}>
          <DialogHeader>
            <DialogTitle>Re-index the library?</DialogTitle>
            <DialogDescription>
              Every paper's passages are embedded again with {status.data?.model}, in the background.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button variant="destructive" disabled={reindex.isPending} onClick={() => void confirmReindex()}>
              Re-index
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
