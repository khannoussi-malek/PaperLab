import { useEmbeddingStatus } from '@/api/queries'
import { delayedIn } from '@/components/motion'
import { Alert, AlertAction, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { DownloadSearchModel } from '@/features/settings/DownloadSearchModel'
import { useSearchModelDownload } from '@/features/settings/useSearchModelDownload'
import { cn } from '@/lib/utils'
import { BUILT_IN_SEARCH } from './setup'
import { StepButtons } from './StepButtons'

/**
 * Step 2 (spec §5, D179): the built-in search model, downloaded here with the search model download's own button and
 * progress, or Skip. Finish waits while the download runs; Skip leaves search for Settings → Search.
 */
export function SetupSearch({ onFinish }: { onFinish: () => void }) {
  const status = useEmbeddingStatus()
  const { state } = useSearchModelDownload()

  return (
    <section aria-labelledby="setup-search-heading" className="flex flex-col gap-4">
      <h2 id="setup-search-heading" className="font-heading text-xl font-semibold">
        Search
      </h2>
      <p className="text-sm text-muted-foreground">
        Search finds the passages that answer a question about a long paper or a workspace. Change it any time in
        Settings → Search.
      </p>
      {status.data !== undefined ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium">Built-in</p>
          <p className="text-sm text-muted-foreground">{BUILT_IN_SEARCH}</p>
          <DownloadSearchModel alwaysShowStatus />
        </div>
      ) : status.isError ? (
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
      )}
      <StepButtons next="Finish" busy={state.status === 'downloading'} onNext={onFinish} />
    </section>
  )
}
