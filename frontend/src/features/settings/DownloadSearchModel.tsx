import { Download } from 'lucide-react'
import { useEmbeddingStatus } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { downloadLabel, downloadPercent, statusLine } from './searchModel'
import { useSearchModelDownload } from './useSearchModelDownload'

/**
 * The built-in search model's Download button, then the download's progress bar and status line, or its error. The
 * same download wherever it shows (Settings → Search, the library notice, chat). `alwaysShowStatus`: show the status
 * line before any download too (Settings); elsewhere it appears once a download starts.
 */
export function DownloadSearchModel({ alwaysShowStatus = false }: { alwaysShowStatus?: boolean }) {
  const status = useEmbeddingStatus()
  const { state, start } = useSearchModelDownload()
  if (status.data === undefined) return null
  const present = status.data.model_present
  return (
    <div className="flex flex-col gap-2">
      {(alwaysShowStatus || state.status !== 'idle') && (
        <p className="search-model-status text-sm tabular-nums text-muted-foreground">{statusLine(present, state)}</p>
      )}
      {state.status === 'downloading' && (
        <Progress aria-label="Downloading the search model" value={downloadPercent(state)} />
      )}
      {!present && (state.status === 'idle' || state.status === 'error') && (
        <div>
          <Button variant="outline" size="sm" onClick={start}>
            <Download aria-hidden />
            {downloadLabel(status.data.download_bytes)}
          </Button>
        </div>
      )}
      {state.status === 'error' && (
        <Alert variant="destructive" className="border-glass-border">
          <AlertDescription>{state.message}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
