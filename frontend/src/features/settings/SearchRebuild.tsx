import { useEmbeddingStatus, useTryAgain } from '@/api/queries'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { errorLine, rebuildLine, rebuildPercent } from './searchSources'

/**
 * P1: "Search is being rebuilt with OpenAI: 12 of 20 papers." and its bar while a switch or a re-index runs. It reads
 * the one embedding status query, which polls every 2 s meanwhile (D156). Nothing once the rebuild is done.
 *
 * A quiet, always-available "Try again" sits next to the line: a stalled rebuild (a job timeout, a worker restart)
 * can sit with nothing recorded in `source_error`, so `SourceError` below never shows and there'd be no way out
 * short of a full Re-index. `useTryAgain`'s `missing_only` retry is a no-op for chunks already done, so offering it
 * unconditionally, whenever a rebuild is in progress, is always safe — not styled as an error, since a rebuild in
 * normal progress isn't one.
 */
export function SearchRebuild({ className }: { className?: string }) {
  const status = useEmbeddingStatus()
  const tryAgain = useTryAgain()
  const rebuild = status.data?.rebuild
  if (!status.data || !rebuild) return null
  return (
    <div className={cn('search-rebuild flex flex-col gap-2', className)}>
      <div className="flex items-center gap-2">
        <p className="text-sm tabular-nums text-muted-foreground">{rebuildLine(status.data.source.label, rebuild)}</p>
        <Button variant="ghost" size="xs" disabled={tryAgain.isPending} onClick={() => tryAgain.mutate()}>
          Try again
        </Button>
      </div>
      <Progress aria-label="Rebuilding search" value={rebuildPercent(rebuild)} />
    </div>
  )
}

/** The last embedding failure (D155) with Try again, which resumes the rebuild for the papers still missing. */
export function SourceError() {
  const status = useEmbeddingStatus()
  const tryAgain = useTryAgain()
  const error = status.data?.source_error
  if (!error) return null
  return (
    <Alert variant="destructive" className="border-glass-border">
      <AlertDescription>{tryAgain.error?.message ?? errorLine(error)}</AlertDescription>
      <AlertAction>
        <Button variant="outline" size="xs" disabled={tryAgain.isPending} onClick={() => tryAgain.mutate()}>
          Try again
        </Button>
      </AlertAction>
    </Alert>
  )
}
