import { useEmbeddingStatus, useTryAgain } from '@/api/queries'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { errorLine, rebuildLine, rebuildPercent } from './searchSources'

/**
 * P1: "Search is being rebuilt with OpenAI: 12 of 20 papers." and its bar while a switch or a re-index runs. It reads
 * the one embedding status query, which polls every 2 s meanwhile (D156). Nothing once the rebuild is done.
 */
export function SearchRebuild({ className }: { className?: string }) {
  const status = useEmbeddingStatus()
  const rebuild = status.data?.rebuild
  if (!status.data || !rebuild) return null
  return (
    <div className={cn('search-rebuild flex flex-col gap-2', className)}>
      <p className="text-sm tabular-nums text-muted-foreground">{rebuildLine(status.data.source.label, rebuild)}</p>
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
