import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useEmbeddingStatus, useReindexLibrary } from '@/api/queries'
import { glass } from '@/components/glass'
import { delayedIn } from '@/components/motion'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { indexedLine, staleChunks } from './embeddingStatus'
import { SearchRebuild, SourceError } from './SearchRebuild'
import { CloudTag, SearchSourcePicker } from './SearchSourcePicker'
import { reindexDialog, sourceLine } from './searchSources'

/** The "Search" section: which source search embeds with and switching it (D150–D158), the rebuild a switch or a
 * re-index starts, the last embedding failure, what the library is indexed with, and a confirmed re-index. */
export function EmbeddingSettings() {
  const status = useEmbeddingStatus()
  const reindex = useReindexLibrary()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const data = status.data
  const cloudReindex = data === undefined ? null : reindexDialog(data.source, data)

  function openConfirm(open: boolean) {
    if (open) reindex.reset() // clear a previous refusal so a reopened dialog starts clean
    setConfirmOpen(open)
  }

  async function confirmReindex() {
    try {
      await reindex.mutateAsync()
      setConfirmOpen(false)
    } catch {
      // shown below from reindex.error; the dialog stays open so the owner can retry or cancel
    }
  }

  return (
    <section aria-labelledby="search-heading" className="flex flex-col gap-4">
      <h2 id="search-heading" className="font-heading text-xl font-semibold">
        Search
      </h2>

      {data === undefined ? (
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
          <p className={cn('text-muted-foreground', delayedIn)}>Loading…</p>
        )
      ) : (
        <div className="flex flex-col gap-3">
          <p className="search-source-status flex items-center gap-2 text-sm font-medium">
            {sourceLine(data.source)}
            {!data.source.is_local && <CloudTag />}
          </p>
          <SearchSourcePicker key={`${data.source.kind}:${data.source.connection_id}:${data.source.model}`} status={data} />
          <SearchRebuild />
          <SourceError />

          {indexedLine(data) && <p className="embedding-indexed text-xs tabular-nums text-muted-foreground">{indexedLine(data)}</p>}
          {staleChunks(data) > 0 && data.rebuild === null && (
            <Alert variant="destructive" className="border-glass-border">
              <AlertDescription>
                {staleChunks(data)} chunks were indexed with another model. Chat on those papers is refused until you re-index.
              </AlertDescription>
            </Alert>
          )}

          <div>
            {/* With Built-in in use and no model downloaded, a re-index would queue jobs that embed nothing. */}
            <Button
              variant="outline"
              disabled={data.source.kind === 'builtin' && !data.model_present}
              onClick={() => openConfirm(true)}
            >
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

      <Dialog open={confirmOpen} onOpenChange={openConfirm}>
        <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-md')}>
          <DialogHeader>
            <DialogTitle>Re-index the library?</DialogTitle>
            {cloudReindex === null ? (
              <DialogDescription>
                Every paper's passages are embedded again with {data?.model}, in the background.
              </DialogDescription>
            ) : (
              // P2: with a cloud source a re-index sends everything again, so it says what and roughly the cost.
              <DialogDescription asChild>
                <div className="flex flex-col gap-2">
                  {cloudReindex.body.map((sentence) => (
                    <p key={sentence}>{sentence}</p>
                  ))}
                </div>
              </DialogDescription>
            )}
          </DialogHeader>
          {cloudReindex?.footnote.map((sentence) => (
            <p key={sentence} className="text-xs text-muted-foreground">
              {sentence}
            </p>
          ))}
          {reindex.error && (
            <Alert variant="destructive" className="border-glass-border">
              <AlertDescription>{reindex.error.message}</AlertDescription>
            </Alert>
          )}
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
